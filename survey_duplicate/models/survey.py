from odoo import fields, models


class Survey(models.Model):
    """
    Extends the standard Odoo Survey model.

    Adds configuration fields that allow the administrator
    to select which survey questions contain the applicant's
    email address and phone number.
    """

    _inherit = 'survey.survey'

    email_question_id = fields.Many2one(
        comodel_name='survey.question',
        string='Email Question',
        domain="[('survey_id', '=', id)]",
        help='Select the question used to collect the applicant email.'
    )

    phone_question_id = fields.Many2one(
        comodel_name='survey.question',
        string='Phone Question',
        domain="[('survey_id', '=', id)]",
        help='Select the question used to collect the applicant phone number.'
    )