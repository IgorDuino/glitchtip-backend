from datetime import timedelta
from django.db.models import Avg, Count
from django_filters import rest_framework as filters
from django.utils.timezone import now

from projects.models import Project

from .models import TransactionGroup


class TransactionGroupFilter(filters.FilterSet):
    start = filters.IsoDateTimeFilter(
        field_name="transactionevent__created",
        lookup_expr="gte",
        label="Transaction start date",
        initial=now() - timedelta(days=7)
    )
    end = filters.IsoDateTimeFilter(
        field_name="transactionevent__created",
        lookup_expr="lte",
        label="Transaction end date",
    )
    project = filters.ModelMultipleChoiceFilter(queryset=Project.objects.all())
    query = filters.CharFilter(
        field_name="transaction",
        lookup_expr="icontains",
        label="Transaction text search",
    )

    def __init__(self, data=None, *args, **kwargs):
        if data is not None:
            data = data.copy()

            for name, f in self.base_filters.items():
                initial = f.extra.get('initial')

                if not data.get(name) and initial:
                    data[name] = initial

        super().__init__(data, *args, **kwargs)

    class Meta:
        model = TransactionGroup
        fields = ["project", "start", "end"]

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        environments = self.request.query_params.getlist("environment")
        if environments:
            queryset = queryset.filter(tags__environment__has_any_keys=environments)

        # This annotation must be applied after any related transactionevent filter
        queryset = queryset.annotate(
            avg_duration=Avg("transactionevent__duration"),
            transaction_count=Count("transactionevent"),
        )

        return queryset
