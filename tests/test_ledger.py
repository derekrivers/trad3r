from copy import deepcopy
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.ledger import Ledger, replay_ledger
from trad3r.__main__ import main


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.sequence = 0
        self.send('fund', amount='1000')

    def send(self, kind, at='2026-09-04T14:00:00+00:00', **values):
        self.sequence += 1
        event = dict(id=str(self.sequence), type=kind, at=at, **values)
        self.ledger.apply(event)
        return event

    def funded_usd(self):
        self.send('exchange', from_currency='GBP', amount='400', received='500', fee_gbp='1')

    def buy(self, quantity=3, fee='1'):
        self.send('buy', symbol='AAA', quantity=quantity, price='100', fee_usd=fee, usd_to_gbp='0.8')

    def value(self, price='110', fx='0.8', **kw):
        prices = {'AAA': price} if self.ledger.position else {}
        self.send('value', usd_to_gbp=fx, prices=prices, **kw)
        return self.ledger.last_report

    def test_equity_cash_fx_fees_and_unrealised_pnl(self):
        self.funded_usd()
        self.buy()
        result = self.value()
        self.assertEqual(result['settled_cash'], {'GBP': D('599'), 'USD': D('199')})
        self.assertEqual(result['position']['basis_gbp'], D('240.8'))
        self.assertEqual(result['equity_gbp'], D('1022.2'))
        self.assertEqual(result['unrealised_position_pnl_gbp'], D('23.2'))
        self.assertEqual(result['account_pnl_gbp'], D('22.2'))
        self.assertEqual(self.value(fx='0.9')['equity_gbp'], D('1075.1'))

    def test_partial_sales_allocate_all_basis_and_settlement_preserves_equity(self):
        self.funded_usd()
        self.buy()
        for quantity in (1, 2):
            self.send('sell', symbol='AAA', quantity=quantity, price='110', fee_usd='1',
                      usd_to_gbp='0.8', settles_on='2026-09-08')
        result = self.value()
        self.assertIsNone(result['position'])
        self.assertEqual(result['realised_trade_pnl_gbp'], D('21.6'))
        self.assertEqual(result['account_pnl_gbp'], D('20.6'))
        self.assertEqual(result['unsettled_usd'], D('328'))
        self.send('settle', at='2026-09-06T00:00:00+00:00')
        self.assertEqual(self.ledger.cash['USD'], D('199'))
        self.send('settle', at='2026-09-09T04:00:00+00:00')
        after = self.value(at='2026-09-09T04:00:00+00:00')
        self.assertEqual(after['equity_gbp'], result['equity_gbp'])
        self.assertEqual(after['settled_cash']['USD'], D('527'))
        self.assertEqual(after['unsettled_usd'], 0)
        self.send('settle', at='2026-09-09T04:00:00+00:00')
        self.assertEqual(self.ledger.cash['USD'], D('527'))

    def test_external_flows_do_not_create_profit(self):
        self.send('deposit', currency='USD', amount='125', usd_to_gbp='0.8')
        self.send('withdraw', currency='USD', amount='25', usd_to_gbp='0.8')
        result = self.value()
        self.assertEqual(result['account_pnl_gbp'], 0)
        self.assertEqual(result['deposits_gbp'], 100)
        self.assertEqual(result['withdrawals_gbp'], 20)

    def test_unsettled_proceeds_cannot_be_spent_withdrawn_or_exchanged(self):
        self.funded_usd()
        self.buy(quantity=4)
        self.send('sell', symbol='AAA', quantity=4, price='100', fee_usd='1',
                  usd_to_gbp='0.8', settles_on='2026-09-08')
        for kind, payload in (
            ('buy', dict(symbol='AAA', quantity=2, price='100', fee_usd='0', usd_to_gbp='0.8')),
            ('withdraw', dict(currency='USD', amount='100', usd_to_gbp='0.8')),
            ('exchange', dict(from_currency='USD', amount='100', received='80', fee_gbp='0'))):
            before = deepcopy(self.ledger)
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'settled'):
                self.send(kind, **payload)
            self.assertEqual(self.ledger, before)

    def test_rejected_exchange_rolls_back_both_balances(self):
        before = deepcopy(self.ledger)
        with self.assertRaisesRegex(ValueError, 'settled'):
            self.send('exchange', from_currency='GBP', amount='1000', received='1250', fee_gbp='1')
        self.assertEqual(self.ledger, before)

    def test_funding_duplicates_and_out_of_order_rejected(self):
        for kind, payload in (
            ('fund', dict(amount='1000')),
            ('value', dict(at='2026-09-03T14:00:00+00:00', usd_to_gbp='0.8', prices={}))):
            with self.assertRaises(ValueError):
                self.send(kind, **payload)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.ledger.apply({'id': '1', 'type': 'fund', 'at': '2026-09-04T14:00:00Z', 'amount': '1000'})
        with self.assertRaises(ValueError):
            Ledger().apply({'id':'x','type':'fund','at':'2026-09-04T14:00:00Z','amount':'999'})

    def test_short_sale_second_symbol_fractional_quantity_and_invalid_values_rejected(self):
        self.funded_usd()
        self.buy()
        for payload in (dict(symbol='BBB', quantity=1), dict(symbol='AAA', quantity=0.5),
                        dict(symbol='AAA', quantity=True)):
            with self.assertRaises(ValueError):
                self.send('buy', **payload, price='1', fee_usd='0', usd_to_gbp='0.8')
        with self.assertRaises(ValueError):
            self.send('sell', symbol='AAA', quantity=4, price='100', fee_usd='0',
                      usd_to_gbp='0.8', settles_on='2026-09-07')
        for price in ('NaN', '-1', 1.5):
            with self.assertRaises(ValueError):
                self.value(price=price)

    def test_current_complete_valuation_required(self):
        self.funded_usd()
        self.buy()
        with self.assertRaisesRegex(ValueError, 'held symbol'):
            self.send('value', usd_to_gbp='0.8', prices={})
        self.value()
        self.send('deposit', currency='GBP', amount='1', usd_to_gbp='0.8')
        self.assertIsNone(self.ledger.last_report)
        with self.assertRaisesRegex(ValueError, 'end with a value'):
            replay_ledger([])

    def test_cli_synthetic_example_is_repeatable(self):
        args = ['ledger', 'examples/ledger.json']
        outputs = []
        for _ in range(2):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(args), 0)
            outputs.append(out.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(D(json.loads(outputs[0])['account_pnl_gbp']), D('5.4'))

    def test_cli_rejects_bad_event_without_partial_report(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / 'bad.json'
            p.write_text('[{"id":"x","type":"fund","at":"2026-09-04T14:00:00Z","amount":"NaN"}]')
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['ledger', str(p)]), 2)
            self.assertEqual(out.getvalue(), '')
