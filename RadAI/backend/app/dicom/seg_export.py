"""RadAI — DICOM-SEG structure mapping and metadata definitions."""

from pydicom.sr.codedict import codes
from highdicom.content import AlgorithmIdentificationSequence
from highdicom.seg.content import SegmentDescription

# Mapping TotalSegmentator label names to SNOMED CT / DICOM anatomy codes.
# Sprint 1 subset; full list covers 117 structures.
#
# NOTE: pydicom's `codes.SCT` exposes only a limited keyword set. Neither
# "Entire*" qualifiers nor most laterality variants like `RightKidney`,
# `LeftAdrenalGland`, `UpperLobeOfLeftLung`, etc. exist as attributes.
# Probing against pydicom 3.x shows that only the parent codes (`Kidney`,
# `AdrenalGland`, `Lung`) and `MiddleLobeOfRightLung` resolve. We therefore
# map laterality variants to their parent anatomic code — laterality is
# still preserved in `segment_label` so downstream viewers can disambiguate.
# DICOM-SEG export was previously crashing with
# `AttributeError: No matching code for keyword 'RightKidney'` because of
# the optimistic tuple form that predated this probe.
STRUCTURE_MAPPING = {
    "spleen": codes.SCT.Spleen,
    "kidney_right": codes.SCT.Kidney,
    "kidney_left": codes.SCT.Kidney,
    "gallbladder": codes.SCT.Gallbladder,
    "liver": codes.SCT.Liver,
    "stomach": codes.SCT.Stomach,
    "pancreas": codes.SCT.Pancreas,
    "adrenal_gland_right": codes.SCT.AdrenalGland,
    "adrenal_gland_left": codes.SCT.AdrenalGland,
    "lung_upper_lobe_left": codes.SCT.Lung,
    "lung_lower_lobe_left": codes.SCT.Lung,
    "lung_upper_lobe_right": codes.SCT.Lung,
    "lung_middle_lobe_right": codes.SCT.MiddleLobeOfRightLung,
    "lung_lower_lobe_right": codes.SCT.Lung,
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
    concept = STRUCTURE_MAPPING.get(label_name, codes.SCT.Organ)

    return SegmentDescription(
        segment_number=segment_number,
        segment_label=label_name,
        segmented_property_category=codes.SCT.Organ,
        segmented_property_type=concept,
        algorithm_type="AUTOMATIC",
        algorithm_identification=AlgorithmIdentificationSequence(
            name="TotalSegmentator",
            version="2.13",
            family=codes.cid7162.ArtificialIntelligence,
        ),
        anatomic_regions=[concept],
    )
