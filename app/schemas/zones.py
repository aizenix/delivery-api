from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Ring = Annotated[list[tuple[float, float]], Field(min_length=4)]


class GeoJSONPolygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[Ring] = Field(min_length=1)

    @field_validator("coordinates")
    @classmethod
    def rings_are_closed(cls, rings: list[list[tuple[float, float]]]):
        if any(ring[0] != ring[-1] for ring in rings):
            raise ValueError("each ring must start and end with the same point")
        return rings


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    area: GeoJSONPolygon
    delivery_fee: int = Field(ge=0)
    min_order_amount: int = Field(default=0, ge=0)


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    delivery_fee: int
    min_order_amount: int


class ZoneWithArea(ZoneOut):
    area: GeoJSONPolygon = Field(validation_alias="geojson")
