#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright (c) 2008-2024
#  National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

from pyomo.common.log import LoggingIntercept
import pyomo.common.unittest as unittest
from pyomo.core.expr.compare import assertExpressionsEqual
from pyomo.environ import Any, Binary, ConcreteModel, log, Param, Var
from pyomo.repn.linear_wrt import MultilevelLinearRepnVisitor
from pyomo.repn.tests.test_linear import VisitorConfig
from pyomo.repn.util import InvalidNumber


class TestMultilevelLinearRepnVisitor(unittest.TestCase):
    def make_model(self):
        m = ConcreteModel()
        m.x = Var(bounds=(0, 45))
        m.y = Var(domain=Binary)
        m.z = Var()

        return m

    def test_walk_sum(self):
        m = self.make_model()
        e = m.x + m.y
        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)

        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.x), repn.linear)
        self.assertEqual(repn.linear[id(m.x)], 1)
        self.assertIs(repn.constant, m.y)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), m.x + m.y)

    def test_walk_triple_sum(self):
        m = self.make_model()
        e = m.x + m.z * m.y + m.z

        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x, m.y])

        repn = visitor.walk_expression(e)

        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 2)
        self.assertIn(id(m.x), repn.linear)
        self.assertIn(id(m.y), repn.linear)
        self.assertEqual(repn.linear[id(m.x)], 1)
        self.assertIs(repn.linear[id(m.y)], m.z)
        self.assertIs(repn.constant, m.z)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), m.x + m.z * m.y + m.z)

    def test_sum_two_of_the_same(self):
        # This hits the mult == 1 and vid in dest_dict case in _merge_dict
        m = self.make_model()
        e = m.x + m.x
        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x, m.y])

        repn = visitor.walk_expression(e)

        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.x), repn.linear)
        self.assertEqual(repn.linear[id(m.x)], 2)
        self.assertEqual(repn.constant, 0)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), 2*m.x)

    def test_sum_with_mult_0(self):
        m = self.make_model()
        e = 0*m.x + m.x - m.y
        
        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)
        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.x), repn.linear)
        self.assertEqual(repn.linear[id(m.x)], 1)
        assertExpressionsEqual(
            self,
            repn.constant,
            - m.y
        )
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), m.x - m.y)

    def test_sum_nonlinear_to_linear(self):
        m = self.make_model()
        e = m.y * m.x**2 + m.y * m.x - 3

        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)
        assertExpressionsEqual(
            self,
            repn.nonlinear,
            m.y * m.x ** 2
        )
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.x), repn.linear)
        self.assertIs(repn.linear[id(m.x)], m.y)
        self.assertEqual(repn.constant, -3)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), m.y * m.x ** 2
                               + m.y * m.x - 3)

    def test_sum_nonlinear_to_nonlinear(self):
        m = self.make_model()
        e = m.x ** 3 + 3 + m.x**2

        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)
        assertExpressionsEqual(
            self,
            repn.nonlinear,
            m.x ** 3 + m.x ** 2
        )
        self.assertEqual(repn.constant, 3)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), m.x ** 3
                               + m.x ** 2 + 3)

    def test_sum_to_linear_expr(self):
        m = self.make_model()
        e = m.x + m.y * (m.x + 5)

        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.x), repn.linear)
        assertExpressionsEqual(
            self,
            repn.linear[id(m.x)],
            1 + m.y
        )
        assertExpressionsEqual(
            self,
            repn.constant,
            m.y * 5
        )
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(
            self,
            repn.to_expression(visitor), (1 + m.y) * m.x + m.y * 5
        )

    def test_bilinear_term(self):
        m = self.make_model()
        e = m.x * m.y
        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)

        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.x), repn.linear)
        self.assertIs(repn.linear[id(m.x)], m.y)
        self.assertEqual(repn.constant, 0)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), m.y * m.x)

    def test_distributed_bilinear_term(self):
        m = self.make_model()
        e = m.y * (m.x + 7)
        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)

        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.x), repn.linear)
        self.assertIs(repn.linear[id(m.x)], m.y)
        assertExpressionsEqual(self, repn.constant, m.y * 7)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), m.y * m.x + m.y * 7)

    def test_monomial(self):
        m = self.make_model()
        e = 45 * m.y
        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.y])

        repn = visitor.walk_expression(e)

        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.y), repn.linear)
        self.assertEqual(repn.linear[id(m.y)], 45)
        self.assertEqual(repn.constant, 0)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), 45 * m.y)

    def test_constant(self):
        m = self.make_model()
        e = 45 * m.y
        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)

        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 0)
        assertExpressionsEqual(self, repn.constant, 45 * m.y)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), 45 * m.y)

    def test_fixed_var(self):
        m = self.make_model()
        m.x.fix(42)
        e = (m.y**2) * (m.x + m.x**2)

        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)

        self.assertIsNone(repn.nonlinear)
        self.assertEqual(len(repn.linear), 0)
        assertExpressionsEqual(self, repn.constant, (m.y**2) * 1806)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.to_expression(visitor), (m.y**2) * 1806)

    def test_nonlinear(self):
        m = self.make_model()
        e = (m.y * log(m.x)) * (m.y + 2) / m.x

        cfg = VisitorConfig()
        visitor = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x])

        repn = visitor.walk_expression(e)

        self.assertEqual(len(repn.linear), 0)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(self, repn.nonlinear, log(m.x) * (m.y * (m.y + 2)) / m.x)
        assertExpressionsEqual(
            self, repn.to_expression(visitor), log(m.x) * (m.y * (m.y + 2)) / m.x
        )

    def test_finalize(self):
        m = self.make_model()
        m.w = Var()

        e = m.x + 2 * m.w**2 * m.y - m.x - m.w * m.z

        cfg = VisitorConfig()
        repn = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x, m.y, m.z]).walk_expression(e)
        self.assertEqual(cfg.subexpr, {})
        self.assertEqual(cfg.var_map, {id(m.x): m.x, id(m.y): m.y, id(m.z): m.z})
        self.assertEqual(cfg.var_order, {id(m.x): 0, id(m.y): 1, id(m.z): 2})
        self.assertEqual(repn.multiplier, 1)
        self.assertEqual(repn.constant, 0)
        self.assertEqual(len(repn.linear), 2)
        self.assertIn(id(m.y), repn.linear)
        assertExpressionsEqual(
            self,
            repn.linear[id(m.y)],
            2 * m.w ** 2
        )
        self.assertIn(id(m.z), repn.linear)
        assertExpressionsEqual(
            self,
            repn.linear[id(m.z)],
            -m.w
        )
        self.assertEqual(repn.nonlinear, None)

        e *= 5

        cfg = VisitorConfig()
        repn = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x, m.y, m.z]).walk_expression(e)
        self.assertEqual(cfg.subexpr, {})
        self.assertEqual(cfg.var_map, {id(m.x): m.x, id(m.y): m.y, id(m.z): m.z})
        self.assertEqual(cfg.var_order, {id(m.x): 0, id(m.y): 1, id(m.z): 2})
        self.assertEqual(repn.multiplier, 1)
        self.assertEqual(repn.constant, 0)
        self.assertEqual(len(repn.linear), 2)
        self.assertIn(id(m.y), repn.linear)
        print(repn.linear[id(m.y)])
        assertExpressionsEqual(
            self,
            repn.linear[id(m.y)],
            5 * (2 * m.w ** 2)
        )
        self.assertIn(id(m.z), repn.linear)
        assertExpressionsEqual(
            self,
            repn.linear[id(m.z)],
            -5 * m.w
        )
        self.assertEqual(repn.nonlinear, None)

        e = 5 * (m.w * m.y + m.z**2 + 3 * m.w * m.y**3)

        cfg = VisitorConfig()
        repn = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x, m.y, m.z]).walk_expression(e)
        self.assertEqual(cfg.subexpr, {})
        self.assertEqual(cfg.var_map, {id(m.y): m.y, id(m.z): m.z})
        self.assertEqual(cfg.var_order, {id(m.y): 0, id(m.z): 1})
        self.assertEqual(repn.multiplier, 1)
        self.assertEqual(repn.constant, 0)
        self.assertEqual(len(repn.linear), 1)
        self.assertIn(id(m.y), repn.linear)
        assertExpressionsEqual(
            self,
            repn.linear[id(m.y)],
            5 * m.w
        )
        assertExpressionsEqual(self, repn.nonlinear, (m.z**2 + 3 * m.w * m.y**3) * 5)

    def test_ANY_over_constant_division(self):
        m = ConcreteModel()
        m.p = Param(mutable=True, initialize=2, domain=Any)
        m.x = Var()
        m.z = Var()
        m.y = Var()
        # We aren't treating this as a Var, so we don't really care that it's fixed.
        m.y.fix(1)

        expr = m.y + m.x + m.z + ((3 * m.z * m.x) / m.p) / m.y
        cfg = VisitorConfig()
        repn = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x]).walk_expression(expr)

        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(
            self,
            repn.constant,
            m.y + m.z
        )
        self.assertEqual(len(repn.linear), 1)
        print(repn.linear[id(m.x)])
        assertExpressionsEqual(
            self,
            repn.linear[id(m.x)],
            1 + 1.5 * m.z / m.y
        )
        self.assertEqual(repn.nonlinear, None)

    def test_errors_propogate_nan(self):
        m = ConcreteModel()
        m.p = Param(mutable=True, initialize=0, domain=Any)
        m.x = Var()
        m.z = Var()
        m.y = Var()
        m.y.fix(1)

        expr = m.y + m.x + m.z + ((3 * m.z * m.x) / m.p) / m.y
        cfg = VisitorConfig()
        with LoggingIntercept() as LOG:
            repn = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x]).walk_expression(expr)
        self.assertEqual(
            LOG.getvalue(),
            "Exception encountered evaluating expression 'div(3*z, 0)'\n"
            "\tmessage: division by zero\n"
            "\texpression: 3*z*x/p\n",
        )
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(
            self,
            repn.constant,
            m.y + m.z
        )
        self.assertEqual(len(repn.linear), 1)
        self.assertIsInstance(repn.linear[id(m.x)], InvalidNumber)
        assertExpressionsEqual(
            self,
            repn.linear[id(m.x)].value,
            1 + float('nan')/m.y
        )
        self.assertEqual(repn.nonlinear, None)

        m.y.fix(None)
        expr = m.z * log(m.y) + 3
        repn = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x]).walk_expression(expr)
        self.assertEqual(repn.multiplier, 1)
        self.assertIsInstance(repn.constant, InvalidNumber)
        assertExpressionsEqual(
            self,
            repn.constant.value,
            float('nan')*m.z + 3
        )
        self.assertEqual(repn.linear, {})
        self.assertEqual(repn.nonlinear, None)

    def test_negation_constant(self):
        m = self.make_model()
        e = - (m.y * m.z + 17)

        cfg = VisitorConfig()
        repn = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x]).walk_expression(e)

        self.assertEqual(len(repn.linear), 0)
        self.assertEqual(repn.multiplier, 1)
        assertExpressionsEqual(
            self,
            repn.constant,
            - 1 * (m.y * m.z + 17)
        )
        self.assertIsNone(repn.nonlinear)
        
    def test_product_nonlinear(self):
        m = self.make_model()
        e = (m.x ** 2) * (log(m.y) * m.z ** 4) * m.y
        cfg = VisitorConfig()
        repn = MultilevelLinearRepnVisitor(*cfg, wrt=[m.x, m.z]).walk_expression(e)

        self.assertEqual(len(repn.linear), 0)
        self.assertEqual(repn.multiplier, 1)
        self.assertEqual(repn.constant, 0)
        print(repn.nonlinear)
        assertExpressionsEqual(
            self,
            repn.nonlinear,
            (m.x ** 2) * (m.z ** 4 * log(m.y)) * m.y
        )
