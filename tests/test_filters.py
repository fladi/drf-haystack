# -*- coding: utf-8 -*-
#
# Unit tests for the `drf_haystack.filters` classes.
#

from __future__ import absolute_import, unicode_literals

import json
from unittest2 import skipIf

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from rest_framework import status
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from drf_haystack.viewsets import HaystackViewSet
from drf_haystack.serializers import HaystackSerializer
from drf_haystack.filters import (
    HaystackAutocompleteFilter, HaystackBoostFilter,
    HaystackGEOSpatialFilter, HaystackHighlightFilter
)

from . import geospatial_support
from .constants import MOCKLOCATION_DATA_SET_SIZE, MOCKPERSON_DATA_SET_SIZE
from .mockapp.models import MockLocation, MockPerson
from .mockapp.search_indexes import MockLocationIndex, MockPersonIndex

factory = APIRequestFactory()


class HaystackFilterTestCase(TestCase):

    fixtures = ["mockperson"]

    def setUp(self):
        MockPersonIndex().reindex()

        class Serializer1(HaystackSerializer):

            class Meta:
                index_classes = [MockPersonIndex]
                fields = ["text", "firstname", "lastname", "full_name", "autocomplete"]
                field_aliases = {
                    "q": "autocomplete",
                    "name": "full_name"
                }

        class Serializer2(HaystackSerializer):

            class Meta:
                index_classes = [MockLocationIndex]
                exclude = ["lastname"]

        class Serializer4(serializers.Serializer):
            # This is not allowed. Must implement a `Meta` class.
            pass

        class ViewSet1(HaystackViewSet):
            index_models = [MockPerson]
            serializer_class = Serializer1
            # No need to specify `filter_backends`, defaults to HaystackFilter

        class ViewSet2(ViewSet1):
            serializer_class = Serializer2

        class ViewSet3(ViewSet1):
            serializer_class = Serializer4

        self.view1 = ViewSet1
        self.view2 = ViewSet2
        self.view3 = ViewSet3

    def tearDown(self):
        MockPersonIndex().clear()

    def test_filter_no_query_parameters(self):
        request = factory.get(path="/", data="", content_type="application/json")
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), MOCKPERSON_DATA_SET_SIZE)

    def test_filter_single_field(self):
        request = factory.get(path="/", data={"firstname": "John"})  # Should return 3 results
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_filter_single_field_with_lookup(self):
        request = factory.get(path="/", data={"firstname__startswith": "John"})  # Should return 3 results
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_filter_aliased_field(self):
        request = factory.get(path="/", data={"name": "John McClane"}, content_type="application/json")
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_aliased_field_with_lookup(self):
        request = factory.get(path="/", data={"name__contains": "John McClane"}, content_type="application/json")
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_single_field_OR(self):
        # Test filtering a single field for multiple values. The parameters should be OR'ed
        request = factory.get(path="/", data={"lastname": "Hickman,Hood"})  # Should return 3 results
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_filter_single_field_OR_custom_lookup_sep(self):
        setattr(self.view1, "lookup_sep", ";")
        request = factory.get(path="/", data={"lastname": "Hickman;Hood"})  # Should return 3 results
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

        # Reset the `lookup_sep`
        setattr(self.view1, "lookup_sep", ",")

    def test_filter_multiple_fields(self):
        # Test filtering multiple fields. The parameters should be AND'ed
        request = factory.get(path="/", data={"lastname": "Hood", "firstname": "Bruno"})  # Should return 1 result
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_multiple_fields_OR_same_fields(self):
        # Test filtering multiple fields for multiple values. The values should be OR'ed between
        # same parameters, and AND'ed between them
        request = factory.get(path="/", data={
            "lastname": "Hickman,Hood",
            "firstname": "Walker,Bruno"
        })  # Should return 2 result
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_filter_excluded_field(self):
        request = factory.get(path="/", data={"lastname": "Hood"}, content_type="application/json")
        response = self.view2.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), MOCKPERSON_DATA_SET_SIZE)  # Should return all results since, field is ignored

    def test_filter_with_non_searched_excluded_field(self):
        request = factory.get(path="/", data={"text": "John"}, content_type="application/json")
        response = self.view2.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)

    def test_filter_raise_on_serializer_without_meta_class(self):
        # Make sure we're getting an ImproperlyConfigured when trying to filter on a viewset
        # with a serializer without `Meta` class.
        request = factory.get(path="/", data={"lastname": "Hood"}, content_type="application/json")
        self.assertRaises(
            ImproperlyConfigured,
            self.view3.as_view(actions={"get": "list"}), request
        )

    def test_filter_unicode_characters(self):
        request = factory.get(path="/", data={"firstname": "åsmund", "lastname": "sørensen"},
                              content_type="application/json")
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(len(response.data), 1)

    def test_filter_negated_field(self):
        request = factory.get(path="/", data={"text__not": "John"}, content_type="application/json")
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 97)

    def test_filter_negated_field_with_lookup(self):
        request = factory.get(path="/", data={"name__not__contains": "John McClane"}, content_type="application/json")
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 99)

    def test_filter_negated_field_with_other_field(self):
        request = factory.get(path="/", data={"firstname": "John", "lastname__not": "McClane"}, content_type="application/json")
        response = self.view1.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

class HaystackAutocompleteFilterTestCase(TestCase):

    fixtures = ["mockperson"]

    def setUp(self):
        MockPersonIndex().reindex()

        class Serializer(HaystackSerializer):

            class Meta:
                index_classes = [MockPersonIndex]
                fields = ["text", "firstname", "lastname", "autocomplete"]

        class ViewSet(HaystackViewSet):
            index_models = [MockPerson]
            serializer_class = Serializer
            filter_backends = [HaystackAutocompleteFilter]

        self.view = ViewSet

    def tearDown(self):
        MockPersonIndex().clear()

    def test_filter_autocomplete_single_term(self):
        # Test querying the autocomplete field for a partial term. Should return 4 results
        request = factory.get(path="/", data={"autocomplete": "jer"}, content_type="application/json")
        response = self.view.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 4)

    def test_filter_autocomplete_multiple_terms(self):
        # Test querying the autocomplete field for multiple terms.
        # Make sure the filter AND's the terms on spaces, thus reduce the results.
        request = factory.get(path="/", data={"autocomplete": "joh mc"}, content_type="application/json")
        response = self.view.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_filter_autocomplete_multiple_parameters(self):
        request = factory.get(path="/", data={"autocomplete": "jer fowler", "firstname": "jeremy"},
                              content_type="application/json")
        response = self.view.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_filter_autocomplete_single_field_OR(self):
        request = factory.get(path="/", data={"autocomplete": "jer,fowl"}, content_type="application/json")
        response = self.view.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@skipIf(not geospatial_support, "Skipped due to lack of GEO spatial features")
class HaystackGEOSpatialFilterTestCase(TestCase):

    fixtures = ["mocklocation"]

    def setUp(self):
        MockLocationIndex().reindex()

        class Serializer(HaystackSerializer):

            class Meta:
                index_classes = [MockLocationIndex]
                fields = [
                    "text", "address", "city", "zip_code",
                    "coordinates",
                ]

        class ViewSet(HaystackViewSet):
            index_models = [MockLocation]
            serializer_class = Serializer
            filter_backends = [HaystackGEOSpatialFilter]

        self.view = ViewSet

    def tearDown(self):
        MockLocationIndex().clear()

    def test_filter_dwithin(self):
        request = factory.get(path="/", data={"from": "59.923396,10.739370", "km": 1}, content_type="application/json")
        response = self.view.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 4)

    def test_filter_dwithin_without_range_unit(self):
        # If no range unit is supplied, no filtering will occur. Make sure we
        # get the entire data set.
        request = factory.get(path="/", data={"from": "59.923396,10.739370"}, content_type="application/json")
        response = self.view.as_view(actions={"get": "list"})(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), MOCKLOCATION_DATA_SET_SIZE)

    def test_filter_dwithin_invalid_params(self):
        request = factory.get(path="/", data={"from": "i am not numeric,10.739370", "km": 1}, content_type="application/json")
        self.assertRaises(
            ValueError,
            self.view.as_view(actions={"get": "list"}), request
        )


class HaystackHighlightFilterTestCase(TestCase):

    fixtures = ["mockperson"]

    def setUp(self):
        MockPersonIndex().reindex()

        class Serializer(HaystackSerializer):

            class Meta:
                index_classes = [MockPersonIndex]
                fields = ["firstname", "lastname"]

        class ViewSet(HaystackViewSet):
            index_models = [MockPerson]
            serializer_class = Serializer
            filter_backends = [HaystackHighlightFilter]

        self.view = ViewSet

    def tearDown(self):
        MockPersonIndex().clear()

    def test_filter_sq_highlighter_filter(self):
        request = factory.get(path="/", data={"firstname": "jeremy"}, content_type="application/json")
        response = self.view.as_view(actions={"get": "list"})(request)
        response.render()
        for result in json.loads(response.content.decode()):
            self.assertTrue("highlighted" in result)
            self.assertEqual(
                result["highlighted"],
                " ".join(("<em>Jeremy</em>", "%s\n" % result["lastname"]))
            )


class HaystackBoostFilterTestCase(TestCase):

    fixtures = ["mockperson"]

    def setUp(self):
        MockPersonIndex().reindex()

        class Serializer(HaystackSerializer):

            class Meta:
                index_classes = [MockPersonIndex]
                fields = ["firstname", "lastname"]

        class ViewSet(HaystackViewSet):
            index_models = [MockPerson]
            serializer_class = Serializer
            filter_backends = [HaystackBoostFilter]

        self.view = ViewSet

    def tearDown(self):
        MockPersonIndex().clear()

    # Skipping the boost filter test case because it fails.
    # I strongly believe that this has to be fixed upstream, and
    # that the drf-haystack code works as it should.

    # def test_filter_boost(self):
    #
    #     # This test will fail
    #     # See https://github.com/django-haystack/django-haystack/issues/1235
    #
    #     request = factory.get(path="/", data={"lastname": "hood"}, content_type="application/json")
    #     response = self.view.as_view(actions={"get": "list"})(request)
    #     response.render()
    #     data = json.loads(response.content.decode())
    #     self.assertEqual(len(response.data), 2)
    #     self.assertEqual(data[0]["firstname"], "Bruno")
    #     self.assertEqual(data[1]["firstname"], "Walker")
    #
    #     # We're boosting walter slightly which should put him first in the results
    #     request = factory.get(path="/", data={"lastname": "hood", "boost": "walker,1.1"},
    #                           content_type="application/json")
    #     response = self.view.as_view(actions={"get": "list"})(request)
    #     response.render()
    #     data = json.loads(response.content.decode())
    #     self.assertEqual(len(response.data), 2)
    #     self.assertEqual(data[0]["firstname"], "Walker")
    #     self.assertEqual(data[1]["firstname"], "Bruno")

    def test_filter_boost_invalid_params(self):
        request = factory.get(path="/", data={"boost": "bruno,i am not numeric!"}, content_type="application/json")
        self.assertRaises(
            ValueError,
            self.view.as_view(actions={"get": "list"}), request
        )
