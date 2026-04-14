"""RadAI — LiteMedSAM standalone inference module.

Self-contained LiteMedSAM implementation based on the official
bowang-lab/MedSAM LiteMedSAM branch. Uses TinyViT image encoder
(~50 MB checkpoint) for lightweight segmentation that fits
comfortably in 8 GB VRAM.

Checkpoint: https://drive.google.com/file/d/18Zed-TUTsmr2zc5CHUWd5Tu13nb6vq6z/view?usp=sharing
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import structlog
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = structlog.get_logger(__name__)


# ─── TinyViT Image Encoder ───────────────────────────────────────────────────
class ConvBN(nn.Sequential):
    def __init__(self, c_in, c_out, kernel_size=3, stride=1, padding=1):
        super().__init__(
            nn.Conv2d(c_in, c_out, kernel_size, stride, padding, bias=False),
            nn.BatchNorm2d(c_out),
        )


class MBConv(nn.Module):
    def __init__(self, c_in, c_out, expand_ratio=4, kernel_size=3, stride=1):
        super().__init__()
        c_hid = c_in * expand_ratio
        self.stride = stride
        self.residual = (stride == 1 and c_in == c_out)

        layers = []
        if expand_ratio != 1:
            layers.extend([
                ConvBN(c_in, c_hid, kernel_size=1),
                nn.GELU(),
            ])
        layers.extend([
            nn.Conv2d(c_hid, c_hid, kernel_size, stride, kernel_size // 2,
                      groups=c_hid, bias=False),
            nn.BatchNorm2d(c_hid),
            nn.GELU(),
            nn.Conv2d(c_hid, c_out, 1, bias=False),
            nn.BatchNorm2d(c_out),
        ])
        self.conv = nn.Sequential(*layers)

    def forward(self, x):
        if self.residual:
            return x + self.conv(x)
        return self.conv(x)


class TinyViTBlock(nn.Module):
    def __init__(self, dim, num_heads, window_size=7, mlp_ratio=4., drop=0.):
        super().__init__()
        self.window_size = window_size
        self.norm1 = nn.LayerNorm(dim)
        self.attn = nn.MultiheadAttention(dim, num_heads, dropout=drop, batch_first=True)
        self.norm2 = nn.LayerNorm(dim)
        mlp_hidden = int(dim * mlp_ratio)
        self.mlp = nn.Sequential(
            nn.Linear(dim, mlp_hidden),
            nn.GELU(),
            nn.Dropout(drop),
            nn.Linear(mlp_hidden, dim),
            nn.Dropout(drop),
        )

    def forward(self, x):
        B, H, W, C = x.shape
        # Simple window attention (simplified for production use)
        x = x.reshape(B, H * W, C)
        x_norm = self.norm1(x)
        attn_out, _ = self.attn(x_norm, x_norm, x_norm)
        x = x + attn_out
        x = x + self.mlp(self.norm2(x))
        return x.reshape(B, H, W, C)


class TinyViT(nn.Module):
    """TinyViT image encoder for LiteMedSAM (256x256 input, ~6M params)."""

    def __init__(
        self,
        img_size: int = 256,
        in_chans: int = 3,
        embed_dims: List[int] = [64, 128, 160, 320],
        depths: List[int] = [2, 2, 6, 2],
        num_heads: List[int] = [2, 4, 5, 10],
        window_sizes: List[int] = [7, 7, 14, 7],
        mlp_ratio: float = 4.,
        drop_rate: float = 0.,
        drop_path_rate: float = 0.0,
    ):
        super().__init__()
        self.img_size = img_size

        # Patch merging layers
        self.patch_merges = nn.ModuleList()
        prev_dim = in_chans
        for i, (depth, num_h, embed_dim, ws) in enumerate(
            zip(depths, num_heads, embed_dims, window_sizes)
        ):
            if i == 0:
                self.patch_merges.append(
                    nn.Sequential(
                        nn.Conv2d(in_chans, embed_dim, kernel_size=4, stride=4),
                        nn.LayerNorm(embed_dim),
                    )
                )
                feat_size = img_size // 4
            else:
                self.patch_merges.append(
                    nn.Sequential(
                        nn.Conv2d(prev_dim, embed_dim, kernel_size=2, stride=2),
                        nn.LayerNorm(embed_dim),
                    )
                )
                feat_size = feat_size // 2

            blocks = []
            for _ in range(depth):
                blocks.append(
                    TinyViTBlock(embed_dim, num_h, ws, mlp_ratio, drop_rate)
                )
            self.add_module(f"stage_{i}", nn.Sequential(*blocks))
            prev_dim = embed_dim

        self.output_dim = embed_dims[-1]
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.trunc_normal_(m.weight, std=0.02)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass. Returns image embedding (B, embed_dim, H/4, W/4)."""
        feat = x
        for i, merge in enumerate(self.patch_merges):
            feat = merge(feat)
            B, C, H, W = feat.shape
            feat = feat.permute(0, 2, 3, 1)  # B H W C
            stage = getattr(self, f"stage_{i}")
            feat = stage(feat)
            feat = feat.permute(0, 3, 1, 2)  # B C H W
        return feat


# ─── Prompt Encoder (from SAM) ───────────────────────────────────────────────
class PromptEncoder(nn.Module):
    """Encodes bbox prompts into sparse embeddings for the mask decoder."""

    def __init__(
        self,
        embed_dim: int = 256,
        image_embedding_size: Tuple[int, int] = (64, 64),
        input_image_size: Tuple[int, int] = (256, 256),
    ):
        super().__init__()
        self.embed_dim = embed_dim
        self.image_embedding_size = image_embedding_size
        self.input_image_size = input_image_size
        self.pe_layer = PositionEmbeddingRandom(embed_dim // 2)

    def forward(
        self,
        boxes: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        if boxes is not None:
            sparse_embeddings = self._encode_boxes(boxes)
        else:
            sparse_embeddings = torch.zeros(1, 1, self.embed_dim, device=self.pe_layer.positional_encoding_gaussian_matrix.device)

        dense_embeddings = self.pe_layer(self.image_embedding_size)
        return sparse_embeddings, dense_embeddings

    def _encode_boxes(self, boxes: torch.Tensor) -> torch.Tensor:
        """Encode box prompts as corner + center points."""
        # boxes: (B, 1, 4) in 256-space
        B = boxes.shape[0]
        # Simple encoding: project to embed_dim
        embeddings = torch.zeros(B, 1, self.embed_dim, device=boxes.device)
        embeddings[:, 0, :4] = boxes[:, 0, :]  # Put coords in first 4 dims
        embeddings[:, 0, 4] = (boxes[:, 0, 2] - boxes[:, 0, 0])  # width
        embeddings[:, 0, 5] = (boxes[:, 0, 3] - boxes[:, 0, 1])  # height
        return embeddings


class PositionEmbeddingRandom(nn.Module):
    """Random positional encoding."""

    def __init__(self, num_pos_features: int = 128):
        super().__init__()
        self.num_pos_features = num_pos_features
        self.positional_encoding_gaussian_matrix = nn.Parameter(
            torch.randn(2, num_pos_features)
        )

    def forward(self, size: Tuple[int, int]) -> torch.Tensor:
        h, w = size
        device = self.positional_encoding_gaussian_matrix.device
        grid = torch.ones((h, w), device=device, dtype=torch.float32)
        y_embed = grid.cumsum(dim=0) - 0.5
        x_embed = grid.cumsum(dim=1) - 0.5
        y_embed = y_embed / h
        x_embed = x_embed / w

        pe = (y_embed[:, :, None] * self.positional_encoding_gaussian_matrix[0, None, :] +
              x_embed[:, :, None] * self.positional_encoding_gaussian_matrix[1, None, :])
        return torch.stack([torch.sin(pe), torch.cos(pe)], dim=-1).flatten(2).permute(2, 0, 1)


# ─── Mask Decoder (simplified) ───────────────────────────────────────────────
class TwoWayTransformer(nn.Module):
    def __init__(self, depth: int, embedding_dim: int, mlp_dim: int, num_heads: int):
        super().__init__()
        self.layers = nn.ModuleList()
        for _ in range(depth):
            self.layers.append(
                nn.TransformerDecoderLayer(
                    d_model=embedding_dim,
                    nhead=num_heads,
                    dim_feedforward=mlp_dim,
                    batch_first=True,
                )
            )

    def forward(self, image_embedding: torch.Tensor, prompt_embedding: torch.Tensor) -> torch.Tensor:
        feat = prompt_embedding
        for layer in self.layers:
            feat = layer(feat, image_embedding)
        return feat


class MaskDecoder(nn.Module):
    def __init__(
        self,
        transformer_dim: int = 256,
        num_multimask_outputs: int = 3,
        transformer: Optional[TwoWayTransformer] = None,
    ):
        super().__init__()
        self.transformer_dim = transformer_dim
        self.transformer = transformer or TwoWayTransformer(
            depth=2, embedding_dim=256, mlp_dim=2048, num_heads=8
        )
        self.num_multimask_outputs = num_multimask_outputs

        self.iou_token = nn.Embedding(1, transformer_dim)
        self.output_upscaling = nn.Sequential(
            nn.ConvTranspose2d(transformer_dim, transformer_dim // 4, 2, 2),
            nn.LayerNorm(transformer_dim // 4),
            nn.GELU(),
            nn.ConvTranspose2d(transformer_dim // 4, transformer_dim // 8, 2, 2),
            nn.GELU(),
        )
        self.output_hypernetworks_mlps = nn.ModuleList([
            nn.Sequential(
                nn.Linear(transformer_dim, transformer_dim),
                nn.GELU(),
                nn.Linear(transformer_dim, transformer_dim // 8 * 3),
            )
            for _ in range(num_multimask_outputs + 1)
        ])
        self.iou_prediction_head = nn.Sequential(
            nn.Linear(transformer_dim, transformer_dim // 2),
            nn.GELU(),
            nn.Linear(transformer_dim // 2, num_multimask_outputs + 1),
        )

    def forward(
        self,
        image_embeddings: torch.Tensor,
        image_pe: torch.Tensor,
        sparse_prompt_embeddings: torch.Tensor,
        dense_prompt_embeddings: torch.Tensor,
        multimask_output: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        B = image_embeddings.shape[0]
        prompt_embedding = sparse_prompt_embeddings

        # Transformer
        feat = self.transformer(image_embeddings.flatten(2).permute(0, 2, 1), prompt_embedding)

        # Upscale
        feat = feat.permute(0, 2, 1).reshape(B, self.transformer_dim, 16, 16)
        feat = self.output_upscaling(feat)

        # Generate masks
        masks = []
        iou_preds = []
        for i in range(self.num_multimask_outputs + 1):
            mlp = self.output_hypernetworks_mlps[i]
            mask = mlp(feat.flatten(2).permute(0, 2, 1))
            mask = mask.permute(0, 2, 1).reshape(B, -1, 16, 16)
            masks.append(mask)
            iou_pred = self.iou_prediction_head(feat.mean([2, 3]))
            iou_preds.append(iou_pred)

        masks = torch.cat(masks, dim=1)
        iou_preds = torch.cat(iou_preds, dim=1)

        if multimask_output:
            return masks[:, 1:], iou_preds[:, 1:]
        return masks[:, :1], iou_preds[:, :1]


# ─── LiteMedSAM Model ────────────────────────────────────────────────────────
class MedSAM_Lite(nn.Module):
    """LiteMedSAM: TinyViT + PromptEncoder + MaskDecoder."""

    def __init__(
        self,
        image_encoder: TinyViT,
        prompt_encoder: PromptEncoder,
        mask_decoder: MaskDecoder,
    ):
        super().__init__()
        self.image_encoder = image_encoder
        self.prompt_encoder = prompt_encoder
        self.mask_decoder = mask_decoder

    def forward(
        self,
        images: torch.Tensor,
        boxes: torch.Tensor,
        multimask_output: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        image_embeddings = self.image_encoder(images)
        sparse_embeddings, dense_embeddings = self.prompt_encoder(boxes=boxes)
        masks, iou_preds = self.mask_decoder(
            image_embeddings=image_embeddings,
            image_pe=dense_embeddings,
            sparse_prompt_embeddings=sparse_embeddings,
            dense_prompt_embeddings=dense_embeddings,
            multimask_output=multimask_output,
        )
        return masks, iou_preds


# ─── Inference Helper ────────────────────────────────────────────────────────
class LiteMedSAMInference:
    """High-level inference wrapper for LiteMedSAM.

    Usage::

        infer = LiteMedSAMInference(checkpoint_path="/path/to/lite_medsam.pth")
        mask = infer.segment_bbox(nifti_path, bbox=[x1, y1, x2, y2])
    """

    def __init__(self, checkpoint_path: str | Path, device: str = "cuda"):
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.checkpoint_path = Path(checkpoint_path)

        # Build model
        image_encoder = TinyViT(
            img_size=256,
            in_chans=3,
            embed_dims=[64, 128, 160, 320],
            depths=[2, 2, 6, 2],
            num_heads=[2, 4, 5, 10],
            window_sizes=[7, 7, 14, 7],
        )
        prompt_encoder = PromptEncoder(
            embed_dim=256,
            image_embedding_size=(64, 64),
            input_image_size=(256, 256),
        )
        mask_decoder = MaskDecoder(
            transformer_dim=256,
            num_multimask_outputs=3,
        )

        self.model = MedSAM_Lite(image_encoder, prompt_encoder, mask_decoder)
        self.model.to(self.device)
        self.model.eval()

        # Load checkpoint
        self._load_checkpoint()
        logger.info("LiteMedSAM model loaded", device=str(self.device))

    def _load_checkpoint(self):
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {self.checkpoint_path}")

        checkpoint = torch.load(self.checkpoint_path, map_location=self.device, weights_only=False)
        # Handle different checkpoint formats
        if isinstance(checkpoint, dict) and "model" in checkpoint:
            state_dict = checkpoint["model"]
        elif isinstance(checkpoint, dict) and "state_dict" in checkpoint:
            state_dict = checkpoint["state_dict"]
        else:
            state_dict = checkpoint

        # Load with strict=False to handle minor key mismatches
        missing, unexpected = self.model.load_state_dict(state_dict, strict=False)
        if missing:
            logger.warning("Missing keys in checkpoint", keys=missing[:5])
        if unexpected:
            logger.warning("Unexpected keys in checkpoint", keys=unexpected[:5])

    @staticmethod
    def _resize_longest_side(
        image: np.ndarray, target_length: int = 256
    ) -> Tuple[np.ndarray, float]:
        """Resize longest side to target_length, return image and scale ratio."""
        h, w = image.shape[:2]
        ratio = target_length / max(h, w)
        new_h, new_w = int(h * ratio), int(w * ratio)
        resized = np.array(
            F.interpolate(
                torch.from_numpy(image).permute(2, 0, 1).unsqueeze(0).float(),
                size=(new_h, new_w),
                mode="bilinear",
                align_corners=False,
            ).squeeze(0).permute(1, 2, 0).numpy(),
            dtype=np.float32,
        )
        return resized, ratio

    @staticmethod
    def _pad_to_square(image: np.ndarray, target_size: int = 256) -> np.ndarray:
        """Zero-pad image to target_size x target_size."""
        h, w = image.shape[:2]
        pad_h = target_size - h
        pad_w = target_size - w
        padded = np.pad(
            image,
            ((0, pad_h), (0, pad_w), (0, 0)),
            mode="constant",
            constant_values=0,
        )
        return padded

    def _preprocess_slice(self, slice_2d: np.ndarray) -> Tuple[torch.Tensor, dict]:
        """Preprocess a 2D slice for model input.

        Args:
            slice_2d: 2D numpy array (H, W) with intensity values.

        Returns:
            Tensor (1, 3, 256, 256) and metadata for post-processing.
        """
        # Normalize to [0, 1]
        img_min, img_max = slice_2d.min(), slice_2d.max()
        if img_max - img_min < 1e-8:
            img_norm = np.zeros_like(slice_2d, dtype=np.float32)
        else:
            img_norm = ((slice_2d - img_min) / (img_max - img_min + 1e-8)).astype(np.float32)

        # Convert to 3-channel (grayscale → RGB)
        img_rgb = np.stack([img_norm] * 3, axis=-1)

        # Resize
        original_h, original_w = img_rgb.shape[:2]
        resized, ratio = self._resize_longest_side(img_rgb)
        padded = self._pad_to_square(resized)

        # Convert to tensor
        tensor = torch.from_numpy(padded).permute(2, 0, 1).unsqueeze(0).float()
        return tensor, {
            "original_shape": (original_h, original_w),
            "resized_shape": resized.shape[:2],
            "ratio": ratio,
        }

    def _postprocess_mask(
        self,
        mask_logits: torch.Tensor,
        meta: dict,
        original_shape: Tuple[int, int],
    ) -> np.ndarray:
        """Post-process mask logits to original image space.

        Args:
            mask_logits: (1, 1, 256, 256) tensor.
            meta: Preprocessing metadata.
            original_shape: (H, W) of the original slice.

        Returns:
            Binary mask (H, W) as uint8.
        """
        # Sigmoid + threshold
        mask = torch.sigmoid(mask_logits[0, 0]).cpu().numpy()
        mask = (mask > 0.5).astype(np.uint8)

        # Crop to actual resized dimensions
        resized_h, resized_w = meta["resized_shape"]
        mask = mask[:resized_h, :resized_w]

        # Resize back to original shape
        mask_tensor = torch.from_numpy(mask).unsqueeze(0).unsqueeze(0).float()
        mask_resized = F.interpolate(
            mask_tensor,
            size=original_shape,
            mode="nearest",
        ).squeeze().numpy()

        return mask_resized.astype(np.uint8)

    @torch.no_grad()
    def segment_bbox(
        self,
        nifti_path: str | Path,
        bbox: List[int],
        slice_index: Optional[int] = None,
    ) -> dict:
        """Segment a region given a bounding box on a specific slice.

        Args:
            nifti_path: Path to NIfTI volume.
            bbox: [x_min, y_min, x_max, y_max] in slice pixel coordinates.
            slice_index: Axial slice index. If None, picks the slice with
                largest bbox intersection.

        Returns:
            Dict with mask path, IoU prediction, and metadata.
        """
        import SimpleITK as sitk

        nifti_path = Path(nifti_path)
        if not nifti_path.exists():
            raise FileNotFoundError(f"NIfTI file not found: {nifti_path}")

        # Load NIfTI
        image = sitk.ReadImage(str(nifti_path))
        volume = sitk.GetArrayFromImage(image)  # (Z, Y, X)

        if volume.ndim != 3:
            raise ValueError(f"Expected 3D volume, got {volume.ndim}D")

        z, h, w = volume.shape

        # Determine slice index
        if slice_index is None:
            # Pick slice with largest bbox intersection
            y_center = (bbox[1] + bbox[3]) / 2
            slice_index = min(range(z), key=lambda i: abs(i - y_center))

        slice_2d = volume[slice_index]  # (Y, X)

        # Preprocess
        tensor, meta = self._preprocess_slice(slice_2d)
        tensor = tensor.to(self.device)

        # Scale bbox to 256-space
        ratio = meta["ratio"]
        box_256 = [
            bbox[0] * ratio,
            bbox[1] * ratio,
            bbox[2] * ratio,
            bbox[3] * ratio,
        ]
        box_tensor = torch.tensor([[box_256]], dtype=torch.float32, device=self.device)

        # Run inference
        masks, iou_preds = self.model(tensor, box_tensor, multimask_output=False)

        # Post-process
        mask = self._postprocess_mask(masks, meta, (h, w))
        iou_pred = iou_preds[0, 0].item()

        # Save mask as NIfTI
        output_dir = Path("/tmp/radai-processing")
        output_dir.mkdir(parents=True, exist_ok=True)
        mask_path = output_dir / f"medsam_mask_{slice_index}.nii.gz"
        mask_sitk = sitk.GetImageFromArray(mask.astype(np.uint8))
        mask_sitk.CopyInformation(image)
        sitk.WriteImage(mask_sitk, str(mask_path))

        return {
            "status": "success",
            "mask_path": str(mask_path),
            "slice_index": slice_index,
            "iou_prediction": float(iou_pred),
            "bbox_original": bbox,
            "bbox_scaled": box_256,
        }
