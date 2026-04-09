"""RadAI — DICOM-SEG structure mapping and metadata definitions."""

from pydicom.sr.codedict import codes
from highdicom.seg.content import SegmentDescription

# Mapping TotalSegmentator label names to SNOMED CT / DICOM anatomy codes
# This is a subset for Sprint 1. Full list covers 117 structures.
STRUCTURE_MAPPING = {
    "spleen": (codes.SCT.Spleen, codes.SCT.EntireSpleen),
    "kidney_right": (codes.SCT.RightKidney, codes.SCT.EntireKidney),
    "kidney_left": (codes.SCT.LeftKidney, codes.SCT.EntireKidney),
    "gallbladder": (codes.SCT.Gallbladder, codes.SCT.EntireGallbladder),
    "liver": (codes.SCT.Liver, codes.SCT.EntireLiver),
    "stomach": (codes.SCT.Stomach, codes.SCT.EntireStomach),
    "pancreas": (codes.SCT.Pancreas, codes.SCT.EntirePancreas),
    "adrenal_gland_right": (codes.SCT.RightAdrenalGland, codes.SCT.EntireAdrenalGland),
    "adrenal_gland_left": (codes.SCT.LeftAdrenalGland, codes.SCT.EntireAdrenalGland),
    "lung_upper_lobe_left": (codes.SCT.UpperLobeOfLeftLung, codes.SCT.EntireLobeOfLung),
    "lung_lower_lobe_left": (codes.SCT.LowerLobeOfLeftLung, codes.SCT.EntireLobeOfLung),
    "lung_upper_lobe_right": (codes.SCT.UpperLobeOfRightLung, codes.SCT.EntireLobeOfLung),
    "lung_middle_lobe_right": (codes.SCT.MiddleLobeOfRightLung, codes.SCT.EntireLobeOfLung),
    "lung_lower_lobe_right": (codes.SCT.LowerLobeOfRightLung, codes.SCT.EntireLobeOfLung),
    # ... more mappings can be added here
}

def get_segment_description(label_name: str, segment_number: int) -> SegmentDescription:
    """
    Create a highdicom SegmentDescription for a given TotalSegmentator structure.
    
    Args:
        label_name: The structure name (e.g., 'liver').
        segment_number: The integer ID in the segmentation mask.
        
    Returns:
        highdicom.seg.content.SegmentDescription object.
    """
    if label_name in STRUCTURE_MAPPING:
        concept, anatomical_structure = STRUCTURE_MAPPING[label_name]
    else:
        # Generic fallback for unknown structures
        concept = codes.SCT.Organ 
        anatomical_structure = codes.SCT.AnatomicalStructure
        
    return SegmentDescription(
        segment_number=segment_number,
        segment_label=label_name,
        segmented_property_category=codes.SCT.Organ,
        segmented_property_type=concept,
        algorithm_type="AUTOMATIC",
        algorithm_name="TotalSegmentator v2.13",
        anatomic_regions=[anatomical_structure]
    )
