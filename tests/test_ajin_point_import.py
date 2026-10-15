import importlib.util
from pathlib import Path
import unittest


spec=importlib.util.spec_from_file_location('ajin_import_fixture',Path(__file__).resolve().parents[1]/'tools'/'import_ajin_points.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AjinPointImportTests(unittest.TestCase):
    def test_matches_point_name_not_onu_id_and_preserves_requested_exclusions(self):
        points={number:{'number':number,'address':f'Rua {number}','latitude':-27.44,'longitude':-48.50,'active':True} for number in (6,42,58)}
        rows=[{'name':'Ponto 06','id':'58','port':'PON-1','serial':'AA','map_enabled':False},
              {'name':'Ponto 42','id':'6','port':'PON-1','serial':'BB','desc':'acho q é o ponto 58'}]
        plan=module.prepare(points,rows,{42})
        self.assertEqual(len(plan['changes']),1)
        self.assertEqual(plan['changes'][0]['payload']['id'],'58')
        self.assertEqual(plan['changes'][0]['payload']['desc'],'Rua 6')
        self.assertFalse(plan['changes'][0]['payload']['map_enabled'])
        self.assertEqual(len(plan['pending']),1)
        self.assertEqual(plan['not_registered'][0]['number'],58)

    def test_missing_points_export_with_coordinates_but_always_disabled(self):
        point={'number':58,'address':'Rua A','region':'Jurerê','latitude':-27.4,'longitude':-48.5,'active':True}
        plan={'not_registered':[point]}
        exported=module.inactive_catalog(plan)
        self.assertFalse(exported[0]['map_enabled'])
        self.assertEqual(exported[0]['latitude'],point['latitude'])
        self.assertEqual(exported[0]['address'],point['address'])
        self.assertNotIn('id',exported[0])
        self.assertNotIn('port',exported[0])
        self.assertNotIn('serial',exported[0])
        self.assertTrue(point['active'])

    def test_duplicate_point_names_are_never_assigned_arbitrarily(self):
        points={1:{'number':1}}
        plan=module.prepare(points,[{'name':'Ponto 01','id':1,'port':'A','serial':'AA'}, {'name':'Ponto 1','id':2,'port':'B','serial':'BB'}],set())
        self.assertEqual(plan['changes'],[])
        self.assertEqual(len(plan['pending']),2)

    def test_table_status_and_provided_link_precision_are_preserved(self):
        text='\n'.join([
            '| **Ponto 01** | Rua A | Bairro | `-27.4400000, -48.5000000` | Ativo | [Abrir no Maps](https://www.google.com/maps?q=-27.440000012,-48.500000034) |',
            '| **Ponto 38 (Desativado)** | Rua B | Bairro | `-27.4500000, -48.5100000` | Desativado | [Abrir no Maps](https://www.google.com/maps?q=-27.45,-48.51) |',
        ])
        points=module.parse_mapping(text)
        self.assertEqual(len(points),2)
        self.assertFalse(points[38]['active'])
        self.assertTrue(points[1]['active'])
        self.assertEqual(points[1]['latitude'],-27.440000012)

    def test_bad_coordinates_and_table_link_disagreement_fail_before_any_writes(self):
        line='| **Ponto 01** | Rua | Bairro | `-27.44, -48.50` | Ativo | [Abrir no Maps](https://www.google.com/maps?q=-27.44,-48.50) |'
        self.assertEqual(len(module.parse_mapping(line)),1)
        for invalid in (line.replace('`-27.44','`-97.44'),line.replace('q=-27.44','q=-20.44'),line+'\n'+line):
            with self.assertRaises(ValueError):
                module.parse_mapping(invalid)


if __name__=='__main__':
    unittest.main()
