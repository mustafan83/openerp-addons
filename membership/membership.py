'''Membership'''
##############################################################################
#
# Copyright (c) 2007 TINY SPRL. (http://tiny.be) All Rights Reserved.
#
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

from osv import fields, osv
import time

STATE = [
	('none', 'Non Member'),
	('canceled', 'Canceled Member'),
	('old', 'Old Member'),
	('waiting', 'Waiting Member'),
	('invoiced', 'Invoiced Member'),
	('associated', 'Associated Member'),
	('free', 'Free Member'),
	('paid', 'Paid Member'),
]

STATE_PRIOR = {
		'none' : 0,
		'canceled' : 1,
		'old' : 2,
		'waiting' : 3,
		'invoiced' : 4,
		'associated' : 5,
		'free' : 6,
		'paid' : 7
		}
REQUETE = '''SELECT partner, state FROM (
SELECT members.partner AS partner,
CASE WHEN MAX(members.state) = 0 THEN 'none'
ELSE CASE WHEN MAX(members.state) = 1 THEN 'canceled'
ELSE CASE WHEN MAX(members.state) = 2 THEN 'old'
ELSE CASE WHEN MAX(members.state) = 3 THEN 'waiting'
ELSE CASE WHEN MAX(members.state) = 4 THEN 'invoiced'
ELSE CASE WHEN MAX(members.state) = 5 THEN 'associated'
ELSE CASE WHEN MAX(members.state) = 6 THEN 'free'
ELSE CASE WHEN MAX(members.state) = 7 THEN 'paid'
END END END END END END END END
	AS state FROM (
SELECT partner,
	CASE WHEN MAX(inv_digit.state) = 4 THEN 7
	ELSE CASE WHEN MAX(inv_digit.state) = 3 THEN 4
	ELSE CASE WHEN MAX(inv_digit.state) = 2 THEN 3
	ELSE CASE WHEN MAX(inv_digit.state) = 1 THEN 1
END END END END
AS state
FROM (
	SELECT p.id as partner,
	CASE WHEN ai.state = 'paid' THEN 4
	ELSE CASE WHEN ai.state = 'open' THEN 3
	ELSE CASE WHEN ai.state = 'proforma' THEN 2
	ELSE CASE WHEN ai.state = 'draft' THEN 2
	ELSE CASE WHEN ai.state = 'cancel' THEN 1
END END END END END
AS state
FROM res_partner p
JOIN account_invoice ai ON (
	p.id = ai.partner_id
)
JOIN account_invoice_line ail ON (
	ail.invoice_id = ai.id
)
JOIN membership_membership_line ml ON (
	ml.account_invoice_line  = ail.id
)
WHERE ml.date_from <= '%s'
AND ml.date_to >= '%s'
GROUP BY
p.id,
state
	)
	AS inv_digit
	GROUP by partner
UNION
SELECT p.id AS partner,
	CASE WHEN  p.free_member THEN 6
	ELSE CASE WHEN p.associate_member IN (
		SELECT ai.partner_id FROM account_invoice ai JOIN
		account_invoice_line ail ON (ail.invoice_id = ai.id AND ai.state = 'paid')
		JOIN membership_membership_line ml ON (ml.account_invoice_line = ail.id)
		WHERE ml.date_from <= '%s'
		AND ml.date_to >= '%s'
	)
	THEN 5
END END
AS state
FROM res_partner p
WHERE p.free_member
OR p.associate_member > 0
UNION
SELECT p.id as partner,
	MAX(CASE WHEN ai.state = 'paid' THEN 2
	ELSE 0
	END)
AS state
FROM res_partner p
JOIN account_invoice ai ON (
	p.id = ai.partner_id
)
JOIN account_invoice_line ail ON (
	ail.invoice_id = ai.id
)
JOIN membership_membership_line ml ON (
	ml.account_invoice_line  = ail.id
)
WHERE ml.date_from < '%s'
AND ml.date_to < '%s'
AND ml.date_from <= ml.date_to
GROUP BY
p.id
)
AS members
GROUP BY members.partner
)
AS final
%s
'''

class membership_line(osv.osv):
	'''Member line'''

	def _check_membership_date(self, cr, uid, ids, context=None):
		'''Check if membership product is not in the past'''

		cr.execute('''
		 SELECT MIN(ml.date_to - ai.date_invoice)
		 FROM membership_membership_line ml
		 JOIN account_invoice_line ail ON (
			ml.account_invoice_line = ail.id
			)
		JOIN account_invoice ai ON (
			ai.id = ail.invoice_id)
		WHERE ml.id in (%s)
		''' % ','.join([str(id) for id in ids]))

		res = cr.fetchone()
		for r in res:
			if r[0] < 0:
				return False
		return True

	def _state(self, cr, uid, ids, name, args, context=None):
		'''Compute the state lines'''
		res = {}
		for line in self.browse(cr, uid, ids):
			cr.execute('''
			SELECT i.state FROM
			account_invoice i WHERE
			i.id = (
				SELECT l.invoice_id FROM
				account_invoice_line l WHERE
				l.id = (
					SELECT  ml.account_invoice_line FROM
					membership_membership_line ml WHERE
					ml.id = %d
					)
				)
			''' % line.id)
			fetched = cr.fetchone()
			if not fetched :
				res[line.id] = 'canceled'
				continue
			istate = fetched[0]
			state = 'none'
			if (istate == 'draft') | (istate == 'proforma'):
				state = 'waiting'
			elif istate == 'open':
				state = 'invoiced'
			elif istate == 'paid':
				state = 'paid'
			elif istate == 'cancel':
				state = 'canceled'
			res[line.id] = state
		return res


	_description = __doc__
	_name = 'membership.membership_line'
	_columns = {
			'partner': fields.many2one('res.partner', 'Partner', ondelete='cascade', select=1),
			'date_from': fields.date('From'),
			'date_to': fields.date('To'),
			'date_cancel' : fields.date('Cancel date'),
			'account_invoice_line': fields.many2one('account.invoice.line', 'Account Invoice line'),
			'state': fields.function(_state, method=True, string='State', type='selection', selection=STATE),
			}
	_rec_name = 'partner'
	_order = 'id desc'
	_constraints = [
			(_check_membership_date, 'Error, this membership product is out of date', [])
			]

membership_line()



class Partner(osv.osv):
	'''Partner'''

	def _membership_state(self, cr, uid, ids, name, args, context=None):
		'''Compute membership state of partners'''

		today = time.strftime('%Y-%m-%d')
		res = {}
		for id in ids:
			res[id] = 'none'
		clause = 'WHERE partner IN (' + ','.join([str(id) for id in ids]) + ')'
		cr.execute(REQUETE % (today, today, today, today, today, today, clause))
		fetches = cr.fetchall()
		for fetch in fetches:
			res[fetch[0]] = fetch[1]

		return res

	def _membership_state_search(self, cr, uid, obj, name, args):
		'''Search on membership state'''

		today = time.strftime('%Y-%m-%d')
		clause = 'WHERE '
		for i in range(len(args)):
			if i!=0:
				clause += 'OR '
			clause += 'state '+args[i][1]+" '"+args[i][2]+"' "
		cr.execute(REQUETE % (today, today, today, today, today, today, clause))
		ids=[x[0] for x in cr.fetchall()]

		return [('id', 'in', ids)]

	def _membership_start(self, cr, uid, ids, name, args, context=None):
		'''Return the start date of membership'''
		res = {}
		member_line_obj = self.pool.get('membership.membership_line')
		for partner in self.browse(cr, uid, ids):
			if partner.membership_state == 'associated':
				partner_id = partner.associate_member.id
			else:
				partner_id = partner.id
			line_id = member_line_obj.search(cr, uid, [('partner', '=', partner_id)],
					limit=1, order='date_from ASC')
			if line_id:
				res[partner.id] = member_line_obj.read(cr, uid, line_id[0],
						['date_from'])['date_from']
			else:
				res[partner.id] = False
		return res

	def _membership_start_search(self, cr, uid, obj, name, args):
		'''Search on membership start date'''
		if not len(args):
			return []
		where = ' AND '.join(['date_from '+x[1]+' \''+str(x[2])+'\''
			for x in args])
		cr.execute('SELECT partner, MIN(date_from) \
				FROM ( \
					SELECT partner, MIN(date_from) AS date_from \
					FROM membership_membership_line \
					GROUP BY partner \
				) AS foo \
				WHERE '+where+' \
				GROUP BY partner')
		res = cr.fetchall()
		if not res:
			return [('id', '=', '0')]
		return [('id', 'in', [x[0] for x in res])]

	def _membership_stop(self, cr, uid, ids, name, args, context=None):
		'''Return the stop date of membership'''
		res = {}
		member_line_obj = self.pool.get('membership.membership_line')
		for partner in self.browse(cr, uid, ids):
			if partner.membership_state == 'associated':
				partner_id = partner.associate_member.id
			else:
				partner_id = partner.id
			line_id = member_line_obj.search(cr, uid, [('partner', '=', partner_id)],
					limit=1, order='date_to DESC')
			if line_id:
				res[partner.id] = member_line_obj.read(cr, uid, line_id[0],
						['date_to'])['date_to']
			else:
				res[partner.id] = False
		return res

	def _membership_stop_search(self, cr, uid, obj, name, args):
		'''Search on membership stop date'''
		if not len(args):
			return []
		cr.execute('SELECT partner, MAX(date_to) \
				FROM ( \
					SELECT partner, MAX(date_to) AS date_to \
					FROM membership_membership_line \
					GROUP BY partner \
				) AS foo \
				GROUP BY partner')
		res = cr.fetchall()
		if not res:
			return [('id', '=', '0')]
		return [('id', 'in', [x[0] for x in res])]

	def _membership_cancel(self, cr, uid, ids, name, args, context=None):
		'''Return the cancel date of membership'''
		res = {}
		member_line_obj = self.pool.get('membership.membership_line')
		for partner_id in ids:
			line_id = member_line_obj.search(cr, uid, [('partner', '=', partner_id)],
					limit=1, order='date_cancel ASC')
			if line_id:
				res[partner_id] = member_line_obj.read(cr, uid, line_id[0],
						['date_cancel'])['date_cancel']
			else:
				res[partner_id] = False
		return res

	def _membership_cancel_search(self, cr, uid, obj, name, args):
		'''Search on membership cancel date'''
		if not len(args):
			return []
		where = ' AND '.join(['date_cancel '+x[1]+' \''+str(x[2])+'\''
			for x in args])
		cr.execute('SELECT partner, MIN(date_cancel) \
				FROM ( \
					SELECT partner, MIN(date_cancel) AS date_cancel \
					FROM membership_membership_line \
					GROUP BY partner \
				) AS foo \
				WHERE '+where+' \
				GROUP BY partner')
		res = cr.fetchall()
		if not res:
			return [('id', '=', '0')]
		return [('id', 'in', [x[0] for x in res])]



	_inherit = 'res.partner'
	_columns = {
		'member_lines': fields.one2many('membership.membership_line', 'partner',
			'Membership'),
		'membership_amount': fields.float('Membership amount', digites=(16, 2),
			help='The price negociated by the partner'),
		'membership_state': fields.function(_membership_state, method=True, string='Current membership state',
			type='selection', selection=STATE, fnct_search=_membership_state_search),
		'associate_member': fields.many2one('res.partner', 'Associate member'),
		'free_member': fields.boolean('Free member'),
		'membership_start': fields.function(_membership_start, method=True,
			string='Start membership date', type='date',
			fnct_search=_membership_start_search),
		'membership_stop': fields.function(_membership_stop, method=True,
			string='Stop membership date', type='date',
			fnct_search=_membership_stop_search),
		'membership_cancel': fields.function(_membership_cancel, method=True,
			string='Cancel membership date', type='date',
			fnct_search=_membership_cancel_search),
	}
	_defaults = {
		'free_member': lambda *a: False,
	}

Partner()


class Product(osv.osv):
	'''Product'''

	_inherit = 'product.product'
	_columns = {
			'membership': fields.boolean('Membership', help='Specify if this product is a membership product'),
			'membership_date_from': fields.date('Date from'),
			'membership_date_to': fields.date('Date to'),
			}

	_defaults = {
			'membership': lambda *args: False
			}
Product()

class Invoice(osv.osv):
	'''Invoice'''

	_inherit = 'account.invoice'


	def action_move_create(self, cr, uid, ids, context=None):
		'''Create membership.membership_line if the product is for membership'''
		if context is None:
			context = {}
		member_line_obj = self.pool.get('membership.membership_line')
		partner_obj = self.pool.get('res.partner')
		for invoice in self.browse(cr, uid, ids):

			# fetch already existing member lines
			former_mlines = member_line_obj.search(cr,uid,
					[('account_invoice_line','in',
						[ l.id for l in invoice.invoice_line])], context)
			# empty them :
			if former_mlines:
				member_line_obj.write(cr,uid,former_mlines, {'account_invoice_line':False}, context)

			for line in invoice.invoice_line:
				if line.product_id and line.product_id.membership:
					date_from = line.product_id.membership_date_from
					date_to  = line.product_id.membership_date_to
					if invoice.date_invoice > date_from and invoice.date_invoice < date_to:
						date_from = invoice.date_invoice
					member_line_obj.create(cr, uid, {
						'partner': invoice.partner_id.id,
						'date_from': date_from,
						'date_to': date_to,
						'account_invoice_line': line.id,
						})
		return super(Invoice, self).action_move_create(cr, uid, ids, context)

	def action_cancel(self, cr, uid, ids, context=None):
		'''Create a cancel_date on the membership_line object'''
		
		if context is None:
			context = {}
		member_line_obj = self.pool.get('membership.membership_line')
		today = time.strftime('%Y-%m-%d')

		for invoice in self.browse(cr, uid, ids):
			mlines = member_line_obj.search(cr,uid,
					[('account_invoice_line','in',
						[ l.id for l in invoice.invoice_line])], context)
			member_line_obj.write(cr,uid,mlines, {'cancel_date':today}, context)

Invoice()

#class ReportPartnerMemberProduct(osv.osv):
#	'''Membership by Products'''
#
#	_name = 'report.membership.product'
#	_description = __doc__
#	_auto = False
#	_rec_name = 'product'
#	_columns = {
#		'product': fields.many2one('product.product', 'Membership product', select=1),
#		'state': fields.selection([
#			('draft','Draft'),
#			('proforma','Pro-forma'),
#			('open','Open'),
#			('paid','Paid'),
#			('cancel','Canceled')
#		], 'State', readonly=True, select=1),
#		'number': fields.integer('Number', readonly=True),
#		'price' : fields.float('Price', readonly=True),
##		'amount': fields.float('Amount', digits=(16, 2), readonly=True),
##		'currency': fields.many2one('res.currency', 'Currency', readonly=True,
##			select=2),
#	}
#
#	def init(self, cr):
#		'''Create the view'''
#		cr.execute("""
#			CREATE OR REPLACE VIEW report_membership_product AS (
#				SELECT
#					MIN(l.id) AS id,
#					l.product_id AS product,
#					SUM(l.quantity) AS number,
#					SUM(l.quantity*l.price_unit*(1-l.discount)) AS price,
#					i.state AS state
#				FROM account_invoice_line l
#				LEFT JOIN account_invoice i ON (
#					l.invoice_id=i.id
#					)
#				LEFT JOIN product_product p ON (
#					p.id=l.product_id
#					)
#				WHERE p.membership
#				GROUP BY
#					l.product_id,
#					i.state
#				)""")
#
#ReportPartnerMemberProduct()

class ReportPartnerMemberYear(osv.osv):
	'''Membership by Years'''

	_name = 'report.partner_member.year'
	_description = __doc__
	_auto = False
	_rec_name = 'year'
	_columns = {
		'year': fields.char('Year', size='4', readonly=True, select=1),
		'canceled_number': fields.integer('Canceled', readonly=True),
		'waiting_number': fields.integer('Waiting', readonly=True),
		'invoiced_number': fields.integer('Invoiced', readonly=True),
		'paid_number': fields.integer('Paid', readonly=True),
		'canceled_amount': fields.float('Canceled', digits=(16, 2), readonly=True),
		'waiting_amount': fields.float('Waiting', digits=(16, 2), readonly=True),
		'invoiced_amount': fields.float('Invoiced', digits=(16, 2), readonly=True),
		'paid_amount': fields.float('Paid', digits=(16, 2), readonly=True),
		'currency': fields.many2one('res.currency', 'Currency', readonly=True,
			select=2),
	}

	def init(self, cr):
		'''Create the view'''
		cr.execute("""
	CREATE OR REPLACE VIEW report_partner_member_year AS (
		SELECT
		MIN(id) AS id,
		COUNT(ncanceled) as canceled_number,
		COUNT(npaid) as paid_number,
		COUNT(ninvoiced) as invoiced_number,
		COUNT(nwaiting) as waiting_number,
		SUM(acanceled) as canceled_amount,
		SUM(apaid) as paid_amount,
		SUM(ainvoiced) as invoiced_amount,
		SUM(awaiting) as waiting_amount,
		year,
		currency
		FROM (SELECT
			CASE WHEN ai.state = 'cancel' THEN ml.id END AS ncanceled,
			CASE WHEN ai.state = 'paid' THEN ml.id END AS npaid,
			CASE WHEN ai.state = 'open' THEN ml.id END AS ninvoiced,
			CASE WHEN (ai.state = 'draft' OR ai.state = 'proforma')
				THEN ml.id END AS nwaiting,
			CASE WHEN ai.state = 'cancel'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS acanceled,
			CASE WHEN ai.state = 'paid'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS apaid,
			CASE WHEN ai.state = 'open'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS ainvoiced,
			CASE WHEN (ai.state = 'draft' OR ai.state = 'proforma')
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS awaiting,
			TO_CHAR(ml.date_from, 'YYYY') AS year,
			ai.currency_id AS currency,
			MIN(ml.id) AS id
			FROM membership_membership_line ml
			JOIN (account_invoice_line ail
				LEFT JOIN account_invoice ai
				ON (ail.invoice_id = ai.id))
			ON (ml.account_invoice_line = ail.id)
			JOIN res_partner p
			ON (ml.partner = p.id)
			GROUP BY TO_CHAR(ml.date_from, 'YYYY'), ai.state,
			ai.currency_id, ml.id) AS foo
		GROUP BY year, currency)
				""")

ReportPartnerMemberYear()

class ReportPartnerMemberYearNew(osv.osv):
	'''New Membership by Years'''

	_name = 'report.partner_member.year_new'
	_description = __doc__
	_auto = False
	_rec_name = 'year'

	_columns = {
		'year': fields.char('Year', size='4', readonly=True, select=1),
		'canceled_number': fields.integer('Canceled', readonly=True),
		'waiting_number': fields.integer('Waiting', readonly=True),
		'invoiced_number': fields.integer('Invoiced', readonly=True),
		'paid_number': fields.integer('Paid', readonly=True),
		'canceled_amount': fields.float('Canceled', digits=(16, 2), readonly=True),
		'waiting_amount': fields.float('Waiting', digits=(16, 2), readonly=True),
		'invoiced_amount': fields.float('Invoiced', digits=(16, 2), readonly=True),
		'paid_amount': fields.float('Paid', digits=(16, 2), readonly=True),
		'currency': fields.many2one('res.currency', 'Currency', readonly=True,
			select=2),
	}

	def init(self, cr):
		'''Create the view'''
		cr.execute("""
	CREATE OR REPLACE VIEW report_partner_member_year AS (
		SELECT
		MIN(id) AS id,
		COUNT(ncanceled) as canceled_number,
		COUNT(npaid) as paid_number,
		COUNT(ninvoiced) as invoiced_number,
		COUNT(nwaiting) as waiting_number,
		SUM(acanceled) as canceled_amount,
		SUM(apaid) as paid_amount,
		SUM(ainvoiced) as invoiced_amount,
		SUM(awaiting) as waiting_amount,
		year,
		currency
		FROM (SELECT
			CASE WHEN ai.state = 'cancel' THEN ml.id END AS ncanceled,
			CASE WHEN ai.state = 'paid' THEN ml.id END AS npaid,
			CASE WHEN ai.state = 'open' THEN ml.id END AS ninvoiced,
			CASE WHEN (ai.state = 'draft' OR ai.state = 'proforma')
				THEN ml.id END AS nwaiting,
			CASE WHEN ai.state = 'cancel'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS acanceled,
			CASE WHEN ai.state = 'paid'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS apaid,
			CASE WHEN ai.state = 'open'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS ainvoiced,
			CASE WHEN (ai.state = 'draft' OR ai.state = 'proforma')
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS awaiting,
			TO_CHAR(ml.date_from, 'YYYY') AS year,
			ai.currency_id AS currency,
			MIN(ml.id) AS id
			FROM membership_membership_line ml
			JOIN (account_invoice_line ail
				LEFT JOIN account_invoice ai
				ON (ail.invoice_id = ai.id))
			ON (ml.account_invoice_line = ail.id)
			JOIN res_partner p
			ON (ml.partner = p.id)
			GROUP BY TO_CHAR(ml.date_from, 'YYYY'), ai.state,
			ai.currency_id, ml.id) AS foo
		GROUP BY year, currency)
				""")

ReportPartnerMemberYear()


class ReportPartnerMemberYearNew(osv.osv):
	'''New Membership by Years'''

	_name = 'report.partner_member.year_new'
	_description = __doc__
	_auto = False
	_rec_name = 'year'
	_columns = {
		'year': fields.char('Year', size='4', readonly=True, select=1),
		'canceled_number': fields.integer('Canceled', readonly=True),
		'waiting_number': fields.integer('Waiting', readonly=True),
		'invoiced_number': fields.integer('Invoiced', readonly=True),
		'paid_number': fields.integer('Paid', readonly=True),
		'canceled_amount': fields.float('Canceled', digits=(16, 2), readonly=True),
		'waiting_amount': fields.float('Waiting', digits=(16, 2), readonly=True),
		'invoiced_amount': fields.float('Invoiced', digits=(16, 2), readonly=True),
		'paid_amount': fields.float('Paid', digits=(16, 2), readonly=True),
		'currency': fields.many2one('res.currency', 'Currency', readonly=True,
			select=2),
	}

	def init(self, cursor):
		'''Create the view'''
		cursor.execute("""
		CREATE OR REPLACE VIEW report_partner_member_year_new AS (
		SELECT
		MIN(id) AS id,
		COUNT(ncanceled) AS canceled_number,
		COUNT(npaid) AS paid_number,
		COUNT(ninvoiced) AS invoiced_number,
		COUNT(nwaiting) AS waiting_number,
		SUM(acanceled) AS canceled_amount,
		SUM(apaid) AS paid_amount,
		SUM(ainvoiced) AS invoiced_amount,
		SUM(awaiting) AS waiting_amount,
		year,
		currency
		FROM (SELECT
			CASE WHEN ai.state = 'cancel' THEN ml2.id END AS ncanceled,
			CASE WHEN ai.state = 'paid' THEN ml2.id END AS npaid,
			CASE WHEN ai.state = 'open' THEN ml2.id END AS ninvoiced,
			CASE WHEN (ai.state = 'draft' OR ai.state = 'proforma')
				THEN ml2.id END AS nwaiting,
			CASE WHEN ai.state = 'cancel'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS acanceled,
			CASE WHEN ai.state = 'paid'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS apaid,
			CASE WHEN ai.state = 'open'
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS ainvoiced,
			CASE WHEN (ai.state = 'draft' OR ai.state = 'proforma')
				THEN SUM(ail.price_unit * ail.quantity * (1 - ail.discount / 100))
			ELSE 0 END AS awaiting,
			TO_CHAR(ml2.date_from, 'YYYY') AS year,
			ai.currency_id AS currency,
			MIN(ml2.id) AS id
			FROM (SELECT
					partner AS id,
					MIN(date_from) AS date_from
					FROM membership_membership_line
					GROUP BY partner
				) AS ml1
				JOIN membership_membership_line ml2
				JOIN (account_invoice_line ail
					LEFT JOIN account_invoice ai
					ON (ail.invoice_id = ai.id))
				ON (ml2.account_invoice_line = ail.id)
				ON (ml1.id = ml2.partner AND ml1.date_from = ml2.date_from)
			JOIN res_partner p
			ON (ml2.partner = p.id)
			GROUP BY TO_CHAR(ml2.date_from, 'YYYY'), ai.state,
			ai.currency_id, ml2.id) AS foo
		GROUP BY year, currency
		)
	""")

ReportPartnerMemberYearNew()
