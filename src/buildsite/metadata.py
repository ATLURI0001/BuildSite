"""Site metadata validation and schema extraction."""
from dataclasses import dataclass, asdict
from typing import Dict, Any, List

@dataclass
class SiteMetadata:
    title: str
    slug: str
    tags: List[str]
    is_published: bool = False

    def validate(self) -> bool:
        return bool(self.title.strip() and self.slug.strip())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
