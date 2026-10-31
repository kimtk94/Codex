import unittest
from unittest.mock import MagicMock, patch
from opportunity_ui import LookupSpec, select_lookup, choose_service, fill_guarded, audit_form_labels

class OpportunityUITests(unittest.TestCase):
    def test_lookup_exact_selection(self):
        p=MagicMock()
        inp=MagicMock()
        inp.count.return_value=1;inp.is_visible.return_value=True;inp.is_enabled.return_value=True
        options=MagicMock()
        found=MagicMock();found.count.return_value=1;found.inner_text.return_value="Exact Customer"
        options.filter.return_value=found
        p.locator.side_effect=[inp,options]
        select_lookup(p,LookupSpec("#input",".option"),"Exact","Exact Customer")
        inp.fill.assert_called_once_with("Exact")
        found.click.assert_called_once()

    def test_lookup_ambiguous_rejected(self):
        p=MagicMock()
        inp=MagicMock()
        inp.count.return_value=1;inp.is_visible.return_value=True;inp.is_enabled.return_value=True
        options=MagicMock();found=MagicMock();found.count.return_value=2
        options.filter.return_value=found
        p.locator.side_effect=[inp,options]
        with self.assertRaises(RuntimeError):
            select_lookup(p,LookupSpec("#input",".option"),"Exact","Exact Customer")

    def test_service_already_selected(self):
        p=MagicMock()
        chosen=MagicMock();chosen.get_by_text.return_value.count.return_value=1
        p.locator.return_value=chosen
        self.assertEqual(choose_service(p,"#left","#right","#arrow","Eukaryotic mRNA Sequencing"),"ALREADY_CHOSEN")

    def test_reject_unapproved_picklist(self):
        p=MagicMock()
        with self.assertRaises(ValueError):
            fill_guarded(p, {"Opportunity Name":"N","Amount":"100","Close Date":"2026-11-02","Stage":"Unknown"},
                 {"picklist":{"Stage":{"selector":"#stage","option_selector":".options","allowed_values":["Qualification"]}}})
        p.locator.assert_not_called()

    def test_labels_never_read_field_values(self):
        p=MagicMock()
        p.locator.return_value.all_text_contents.return_value=["Account Name","Stage","Amount"]
        result=audit_form_labels(p)
        self.assertIn("Main Contact",result["unseen_required"])
        p.locator.assert_called_once_with("label")

if __name__=="__main__":
    unittest.main()
