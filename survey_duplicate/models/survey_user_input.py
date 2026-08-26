from odoo import models
from odoo.exceptions import ValidationError


class SurveyUserInput(models.Model):
    """
    Extends survey.user_input to provide duplicate submission prevention.

    The duplicate check is based on the Email Question and Phone Question
    configured on the related survey.

    The class also validates that the configured phone number contains
    exactly 10 numeric digits.
    """

    _inherit = 'survey.user_input'

    def _normalize_email(self, email):
        """
        Normalize an email address before comparison.

        Leading and trailing spaces are removed and the email address
        is converted to lowercase.

        :param email: Email value entered by the applicant.
        :return: Normalized email or False.
        """
        if not email:
            return False

        return str(email).strip().lower()

    def _get_answer_value(self, question):
        """
        Get the answer value of a specific survey question.

        The method checks the answer type and returns the corresponding
        value from survey.user_input.line.

        :param question: survey.question record.
        :return: Answer value or False.
        """
        self.ensure_one()

        if not question:
            return False

        answer_line = self.user_input_line_ids.filtered(
            lambda line: line.question_id == question
        )[:1]

        if not answer_line:
            return False

        line = answer_line

        if line.answer_type == 'char_box':
            return line.value_char_box

        if line.answer_type == 'text_box':
            return line.value_text_box

        if line.answer_type == 'numerical_box':
            return line.value_numerical_box

        return False

    def _raise_duplicate_error(self, message, question):
        """
        Raise a ValidationError while attaching the id of the question
        that caused the error.

        This lets the controller route the error message to the
        correct field on the survey form (email vs phone), instead of
        always showing it under the phone question.

        :param message: Human readable error message.
        :param question: survey.question record related to the error.
        :raise ValidationError: always raises, with a `question_id`
            attribute attached to the exception instance.
        """
        error = ValidationError(message)

        # Attach the related question id directly on the exception
        # instance so the controller can read it in its except block.
        error.question_id = question.id if question else False

        raise error

    def _validate_phone_number(self):
        """
        Validate the phone number entered in the configured phone question.

        The phone number must:
            1. Contain exactly 10 digits.
            2. Contain numeric characters only.
            3. Start with '05', which is the expected Saudi mobile format.

        Example of a valid Saudi mobile number:
            0584521354

        Examples of invalid values:
            058452135       -> Less than 10 digits.
            05845213545     -> More than 10 digits.
            05845abc54      -> Contains non-numeric characters.
            0684521354      -> Does not start with 05.
        """
        self.ensure_one()

        phone_question = self.survey_id.phone_question_id

        # If no phone question is configured, there is nothing to validate.
        if not phone_question:
            return

        phone = self._get_answer_value(phone_question)

        # Mandatory Answer handles empty required questions.
        if not phone:
            return

        phone = str(phone).strip()

        # The phone number must contain exactly 10 numeric digits.
        if not phone.isdigit() or len(phone) != 10:
            self._raise_duplicate_error(
                'يجب أن يتكون رقم الجوال من 10 أرقام بالضبط.',
                phone_question
            )

        # Saudi mobile numbers must start with 05.
        if not phone.startswith('05'):
            self._raise_duplicate_error(
                'يجب أن يبدأ رقم الجوال بـ 05.',
                phone_question
            )

    def _normalize_phone(self, phone):
        """
        Prepare a phone value for duplicate comparison.

        No format conversion is applied (the value is already
        guaranteed to be a clean 10-digit '05XXXXXXXX' number by
        `_validate_phone_number` before this runs) - this only
        guards against comparing non-string types.

        :param phone: Phone value entered by the applicant.
        :return: Stripped phone string or False.
        """
        if not phone:
            return False

        return str(phone).strip()

    def _find_duplicate_submission(self, question, normalize):
        """
        Search for a previous completed submission of the same
        survey that answered the given question with the same
        (normalized) value as the current submission.

        Shared by `_check_duplicate_email` and `_check_duplicate_phone`
        so the search/comparison logic only lives in one place.

        :param question: survey.question record to compare answers on.
        :param normalize: callable used to normalize both the current
            and the previous answer before comparing them.
        :return: Previous duplicate submission or False.
        """
        self.ensure_one()

        if not question:
            return False

        value = normalize(self._get_answer_value(question))

        if not value:
            return False

        # Get completed submissions from the same survey.
        submissions = self.env['survey.user_input'].search([
            ('survey_id', '=', self.survey_id.id),
            ('state', '=', 'done'),
            ('id', '!=', self.id),
        ])

        for submission in submissions:
            previous_value = normalize(
                submission._get_answer_value(question)
            )

            if previous_value and previous_value == value:
                return submission

        return False

    def _check_duplicate_email(self):
        """
        Check whether the current submission uses an email that was
        already used by another completed submission of the same survey.

        :return: Previous duplicate submission or False.
        """
        self.ensure_one()

        return self._find_duplicate_submission(
            self.survey_id.email_question_id,
            self._normalize_email
        )

    def _check_duplicate_phone(self):
        """
        Check whether the current submission uses a phone number that
        was already used by another completed submission of the same survey.

        :return: Previous duplicate submission or False.
        """
        self.ensure_one()

        return self._find_duplicate_submission(
            self.survey_id.phone_question_id,
            self._normalize_phone
        )

    def _check_duplicate_submission(self):
        """
        Validate the current survey submission.

        The validation is performed in the following order:

        1. Validate the phone number format.
        2. Check for duplicate email.
        3. Check for duplicate phone number.

        A ValidationError is raised when a validation fails, with a
        `question_id` attribute attached so the controller can show
        the error message under the correct field.
        """
        self.ensure_one()

        # Validate phone number format.
        # (raises internally via _raise_duplicate_error, tagged with
        # the phone question id)
        self._validate_phone_number()

        # Check for duplicate email.
        duplicate_email = self._check_duplicate_email()

        if duplicate_email:
            self._raise_duplicate_error(
                'تم استخدام هذا البريد الإلكتروني مسبقاً للتقديم '
                'على هذا الاستبيان.',
                self.survey_id.email_question_id
            )

        # Check for duplicate phone number.
        duplicate_phone = self._check_duplicate_phone()

        if duplicate_phone:
            self._raise_duplicate_error(
                'تم استخدام رقم الجوال هذا مسبقاً للتقديم '
                'على هذا الاستبيان.',
                self.survey_id.phone_question_id
            )