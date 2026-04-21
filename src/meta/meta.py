from dataclasses import dataclass, asdict
from typing import List
import json

from meta.batch import Batch
from meta.sample import Sample


@dataclass
class Meta:
    schema: str
    batch: Batch
    samples: List[Sample]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=4)