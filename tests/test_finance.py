import unittest
from aurea.finance import calculate_snapshot, month_key, shift_month, extract_amount

class FinanceTests(unittest.TestCase):
    def test_demo_like_snapshot(self):
        profile={'monthly_income':2000,'investment_pct':10}
        bills=[
            {'id':1,'name':'Aluguel','category':'Moradia','amount':1000,'due_day':5,'kind':'fixed'},
            {'id':2,'name':'Água','category':'Casa','amount':100,'due_day':12,'kind':'fixed'},
            {'id':3,'name':'Cartão','category':'Cartão','amount':750,'due_day':18,'kind':'card'},
        ]
        snap=calculate_snapshot(profile,bills,[],[],[],{},month_key())
        self.assertEqual(snap['metrics']['total_income'],2000.0)
        self.assertEqual(snap['metrics']['committed'],1850.0)
        self.assertEqual(snap['metrics']['suggested_save'],30.0)
        self.assertEqual(snap['metrics']['safe_to_spend'],120.0)

    def test_extra_income_and_budget(self):
        p={'monthly_income':1000,'investment_pct':10}
        tx=[{'amount':200,'tx_type':'income','category':'Freela'}, {'amount':150,'tx_type':'expense','category':'Lazer'}]
        budgets=[{'category':'Lazer','monthly_limit':100}]
        s=calculate_snapshot(p,[],tx,[],budgets,{},month_key())
        self.assertEqual(s['metrics']['total_income'],1200.0)
        self.assertEqual(s['metrics']['variable_spent'],150.0)
        self.assertTrue(s['budgets'][0]['breached'])

    def test_helpers(self):
        self.assertEqual(shift_month('2026-01',-1),'2025-12')
        self.assertEqual(shift_month('2026-12',1),'2027-01')
        self.assertEqual(extract_amount('posso gastar R$ 1.234,56?'),1234.56)

if __name__=='__main__':unittest.main()
