from typing import Annotated, ClassVar

from pydantic import AfterValidator, BaseModel, ConfigDict, HttpUrl, StringConstraints, model_validator

HttpUrlString = Annotated[HttpUrl, AfterValidator(str)]
Text80 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text150 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Text200 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PatchModel(BaseModel):
    """Base model for PATCH requests."""

    model_config = ConfigDict(extra="forbid")
    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")

        invalid = sorted(
            name
            for name in self.model_fields_set
            if name not in self.nullable_fields and getattr(self, name) is None
        )
        if invalid:
            raise ValueError(f"These fields cannot be null: {', '.join(invalid)}")
        return self