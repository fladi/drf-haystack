# -*- coding: utf-8 -*-

from __future__ import absolute_import, unicode_literals

from rest_framework.decorators import detail_route
from rest_framework.response import Response
from rest_framework.viewsets import ViewSetMixin
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin

from .generics import HaystackGenericAPIView


class HaystackViewSet(RetrieveModelMixin, ListModelMixin, ViewSetMixin, HaystackGenericAPIView):
    """
    The HaystackViewSet class provides the default `list()` and
    `retrieve()` actions with a haystack index as it's data source.
    """

    @detail_route(methods=["get"], url_path="more-like-this")
    def more_like_this(self, request, pk=None):
        """
        Sets up a detail route for ``more-like-this`` results.
        Note that you'll need backend support in order to take advantage of this.

        This will add ie. ^search/{pk}/more-like-this/$ to your existing ^search pattern.
        """
        queryset = self.filter_queryset(self.get_queryset())
        mlt_queryset = queryset.more_like_this(self.get_object().object)

        page = self.paginate_queryset(mlt_queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(mlt_queryset, many=True)
        return Response(serializer.data)
