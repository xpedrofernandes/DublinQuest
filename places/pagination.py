from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class GeoJSONPagination(PageNumberPagination):
    """Add page metadata while retaining Leaflet-compatible GeoJSON."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        # DRF GIS many=True already produces a FeatureCollection; don't nest it.
        return Response({"type": "FeatureCollection", "count": self.page.paginator.count,
            "next": self.get_next_link(), "previous": self.get_previous_link(),
            "features": data["features"]})

    def get_paginated_response_schema(self, schema):
        # Keep the generated API documentation consistent with the response above.
        features = schema.get("properties", {}).get("features", schema)
        if "$ref" in schema and schema["$ref"].endswith("List"):
            # DRF GIS documents its list serializer as a FeatureCollection.
            # Pagination needs its feature array, not a nested collection ref.
            features = {"type": "array", "items": {"$ref": schema["$ref"].removesuffix("List")}}
        return {"type": "object", "required": ["type", "count", "features"], "properties": {
            "type": {"type": "string", "enum": ["FeatureCollection"]},
            "count": {"type": "integer"},
            "next": {"type": "string", "nullable": True},
            "previous": {"type": "string", "nullable": True},
            "features": features,
            "search_area": {"type": "object", "description": "EPSG:4326 GeoJSON Polygon; present on park intersection responses only."},
        }}
