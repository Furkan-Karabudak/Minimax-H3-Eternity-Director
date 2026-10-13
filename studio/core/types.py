"""Eternity Studio Core Types and Models.
Completely standalone Python data structures with ZERO legacy dependencies.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class ConceptType(str, Enum):
    CHARACTER = "character"
    ENVIRONMENT = "environment"
    STYLE = "style"
    AUDIO = "audio"
    MOTION = "motion"
    CUSTOM = "custom"


@dataclass
class ConceptItem:
    """Represents an individual concept / global reference element."""
    id: str
    name: str
    concept_type: ConceptType = ConceptType.CHARACTER
    description: str = ""
    # Media references can be in-memory torch tensors, local file paths, or base64 hashes
    image_data: Optional[Any] = None
    video_data: Optional[Any] = None
    audio_data: Optional[Any] = None
    mask_data: Optional[Any] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.concept_type.value,
            "description": self.description,
            "tags": self.tags,
            "metadata": self.metadata,
            "has_image": self.image_data is not None,
            "has_video": self.video_data is not None,
            "has_audio": self.audio_data is not None,
            "has_mask": self.mask_data is not None,
        }


@dataclass
class ConceptBundle:
    """Represents a stackable collection of concepts passed along the ETERNITY_CONCEPTS pin."""
    concepts: Dict[str, ConceptItem] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)

    def add(self, item: ConceptItem, overwrite: bool = True) -> None:
        if item.id not in self.concepts or overwrite:
            self.concepts[item.id] = item
            if item.id not in self.order:
                self.order.append(item.id)

    def merge(self, other: ConceptBundle, overwrite: bool = False) -> ConceptBundle:
        """Merge another bundle into this one, enabling stackable node piping."""
        merged = ConceptBundle(
            concepts=dict(self.concepts),
            order=list(self.order)
        )
        for item_id in other.order:
            item = other.concepts[item_id]
            merged.add(item, overwrite=overwrite)
        return merged

    def to_list(self) -> List[Dict[str, Any]]:
        return [self.concepts[cid].to_dict() for cid in self.order if cid in self.concepts]


@dataclass
class TimelineClip:
    """Represents a clip or shot on a timeline track."""
    id: str
    track_id: str
    start_time: float  # seconds
    duration: float    # seconds
    prompt: str = ""
    negative_prompt: str = ""
    assigned_concept_ids: List[str] = field(default_factory=list)
    camera_motion: str = "static"
    motion_strength: float = 1.0
    transition_in: str = "none"
    transition_duration: float = 0.0
    media_ref: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration


@dataclass
class TimelineTrack:
    """Represents a track in the timeline (video, audio, reference, effect)."""
    id: str
    name: str
    track_type: str = "video"  # "video", "audio", "concept", "overlay"
    muted: bool = False
    locked: bool = False
    clips: List[TimelineClip] = field(default_factory=list)


@dataclass
class TimelineProject:
    """Full data model of an Eternity Studio timeline project."""
    id: str = "default"
    fps: float = 24.0
    width: int = 1280
    height: int = 720
    duration: float = 5.0
    tracks: List[TimelineTrack] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
