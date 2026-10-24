from rest_framework.filters import OrderingFilter


class ModelOrderingFilter(OrderingFilter):
    """Ignore inherited sort fields absent from the current queryset model."""

    def get_valid_fields(self, queryset, view, context=None):
        fields = super().get_valid_fields(queryset, view, context)
        available = {field.name for field in queryset.model._meta.get_fields()}
        available.update(queryset.query.annotations)
        available.add("pk")
        return [(name, label) for name, label in fields if name.split("__")[0] in available]
