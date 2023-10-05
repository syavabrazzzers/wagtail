from io import BytesIO

from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from wagtail.contrib.redirects.models import Redirect
from wagtail.models import Page, Site
from wagtail.test.utils import WagtailTestUtils


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class TestRedirectReport(WagtailTestUtils, TestCase):
    fixtures = ["test.json"]

    def setUp(self):
        self.user = self.login()

        self.page = Page.objects.get(url_path="/home/secret-plans/")

        self.site = Site.objects.first()

    def get(self, params={}):
        return self.client.get(reverse("wagtailredirects:report"), params)

    def test_empty(self):
        response = self.get()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "wagtailredirects/reports/redirects_report.html"
        )
        self.assertContains(response, "No redirects found.")

    def test_listing_contains_redirect(self):
        redirect = Redirect.add_redirect("/from", "/to", False)
        response = self.get()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, redirect.old_path)

    def test_filtering_by_type(self):
        temp_redirect = Redirect.add_redirect("/from", "/to", False)
        perm_redirect = Redirect.add_redirect("/cat", "/dog", True)

        response = self.get(params={"is_permanent": "True"})

        self.assertContains(response, perm_redirect.old_path)
        self.assertNotContains(response, temp_redirect.old_path)

    def test_filtering_by_site(self):
        site_redirect = Redirect.add_redirect("/cat", "/dog")
        site_redirect.site = self.site
        site_redirect.save()
        nosite_redirect = Redirect.add_redirect("/from", "/to")

        response = self.get(params={"site": self.site.pk})

        self.assertContains(response, site_redirect.old_path)
        self.assertNotContains(response, nosite_redirect.old_path)

    def test_csv_export(self):
        Redirect.add_redirect("/from", "/to", False)

        # Session, User, UserProfile, Redirects
        with self.assertNumQueries(4):
            response = self.get(params={"export": "csv"})

            csv_data = response.getvalue().decode().split("\n")

        self.assertEqual(response.status_code, 200)
        csv_header = csv_data[0]
        csv_entries = csv_data[1:]
        csv_entries = csv_entries[:-1]  # Drop empty last line

        self.assertEqual(csv_header, "From,To,Type,Site\r")
        self.assertEqual(len(csv_entries), 1)
        self.assertEqual(csv_entries[0], "/from,/to,temporary,\r")

    def test_xlsx_export(self):
        Redirect.add_redirect("/from", "/to", True)

        # Session, User, UserProfile, Redirects
        with self.assertNumQueries(4):
            response = self.get(params={"export": "xlsx"})
            workbook_data = response.getvalue()

        self.assertEqual(response.status_code, 200)

        worksheet = load_workbook(filename=BytesIO(workbook_data))["Sheet1"]
        cell_array = [[cell.value for cell in row] for row in worksheet.rows]

        self.assertEqual(cell_array[0], ["From", "To", "Type", "Site"])
        self.assertEqual(len(cell_array), 2)
        self.assertEqual(cell_array[1], ["/from", "/to", "permanent", None])

    def test_num_queries(self):
        for i in range(3):
            Redirect.add_redirect(f"/from{i}", "/to", False)
            Redirect.add_redirect(f"/from-site{i}", "/to", False, site=self.site)
            Redirect.add_redirect(f"/to-page{i}", self.page, False)

        # Session, User, UserProfile, Redirects, Site
        with self.assertNumQueries(5):
            response = self.get(params={"export": "csv"})
            csv_data = response.getvalue().decode().strip().split("\n")

        self.assertEqual(len(csv_data), 10)
