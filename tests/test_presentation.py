import unittest
from unittest.mock import patch
from app import presentation
from app.server import Handler,RestrictedAdministration

class PublicPresentation(unittest.TestCase):
    def test_public_summary_preserves_facts_and_input(self):
        row=dict(source_id="camara_ceap",amount="12.34",category="Descrição oficial",description="Texto original",source_url="https://www.camara.leg.br/",verification="confirmed",verification_note="explicação interna",batch_id="internal")
        original=dict(items=[row],coverage=dict(jobs=[dict(error="private-error")],sources=[],coverage=[]),amendments=dict(note="acesso interno"),methodology="internal")
        public=presentation.financial(original)
        for field in ("amount","category","description","source_url","verification"):
            self.assertEqual(public["items"][0][field],row[field])
        self.assertNotIn("batch_id",public["items"][0])
        self.assertEqual(public["coverage"]["jobs"],[])
        self.assertEqual(original["items"][0]["batch_id"],"internal")
        self.assertEqual(original["coverage"]["jobs"][0]["error"],"private-error")
    def test_internal_details_require_global_administrator(self):
        handler=Handler.__new__(Handler)
        for user,exception in [(None,PermissionError),({"role":"admin"},RestrictedAdministration),({"role":"reader"},RestrictedAdministration)]:
            with patch.object(Handler,"current_user",return_value=user):
                with self.assertRaises(exception):handler.technical_view(None,{"technical":"1"})
        with patch.object(Handler,"current_user",return_value={"role":"superadmin"}):
            self.assertTrue(handler.technical_view(None,{"technical":"1"}))
        self.assertFalse(handler.technical_view(None,{}))
