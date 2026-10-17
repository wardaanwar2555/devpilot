from dataclasses import dataclass, field


@dataclass
class Document:
    title: str
    tags: list[str] = field(default_factory=list)

    def add_tag(self, tag: str) -> None:
        if tag not in self.tags:
            self.tags.append(tag)

    def slug(self) -> str:
        return "-".join(self.title.lower().split())
