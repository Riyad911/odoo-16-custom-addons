import json

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError
from odoo.addons.survey.controllers.main import Survey as SurveyController


class SurveyDuplicateController(SurveyController):
    """
    Extend the standard Odoo Survey controller.

    Adds custom validation for:
        - Phone number format
        - Duplicate email
        - Duplicate phone number

    The check now runs as soon as the page containing the Email
    Question and/or Phone Question is submitted, instead of waiting
    until the very last page of the survey. This lets the error
    message show up immediately, inline, under the actual email or
    phone field - the same way standard Odoo required/invalid field
    errors behave - rather than only at the end of the survey.

    Also exposes a small public config route so the frontend JS can
    identify the Email Question / Phone Question fields by their
    question id, since the survey admin can freely choose ANY
    question (with any title wording) as the Email/Phone Question.
    """

    @http.route(
        '/survey_duplicate/config/<string:survey_token>/'
        '<string:answer_token>',
        type='http',
        auth='public',
        website=True,
        methods=['GET'],
        csrf=False,
    )
    def survey_duplicate_config(
        self,
        survey_token,
        answer_token,
        **kwargs
    ):
        """
        Return the ids of the configured Email Question and Phone
        Question for the given survey.

        This lets the frontend JS locate the correct input fields by
        question id, instead of relying on the question's title
        text, which the survey admin can set to any wording.

        :return: JSON response with 'email_question_id' and
            'phone_question_id' (False when not configured).
        """
        access_data = self._get_access_data(
            survey_token,
            answer_token,
            ensure_token=True
        )

        if access_data['validity_code'] is not True:
            config = {
                'email_question_id': False,
                'phone_question_id': False,
            }

        else:
            survey_sudo = access_data['survey_sudo']

            config = {
                'email_question_id': (
                    survey_sudo.email_question_id.id or False
                ),
                'phone_question_id': (
                    survey_sudo.phone_question_id.id or False
                ),
            }

        return request.make_response(
            json.dumps(config),
            headers=[('Content-Type', 'application/json')]
        )

    @http.route(
        '/survey/submit/<string:survey_token>/<string:answer_token>',
        type='json',
        auth='public',
        website=True
    )
    def survey_submit(
        self,
        survey_token,
        answer_token,
        **post
    ):
        """
        Submit survey answers and perform custom validation
        before marking the submission as done.
        """

        # ---------------------------------------------------------
        # 1. Standard Odoo Survey validation
        # ---------------------------------------------------------

        access_data = self._get_access_data(
            survey_token,
            answer_token,
            ensure_token=True
        )

        if access_data['validity_code'] is not True:
            return {'error': access_data['validity_code']}

        survey_sudo = access_data['survey_sudo']
        answer_sudo = access_data['answer_sudo']

        # Submission already completed.
        if answer_sudo.state == 'done':
            return {'error': 'unauthorized'}

        questions, page_or_question_id = (
            survey_sudo._get_survey_questions(
                answer=answer_sudo,
                page_id=post.get('page_id'),
                question_id=post.get('question_id')
            )
        )

        # ---------------------------------------------------------
        # 2. Check remaining attempts
        # ---------------------------------------------------------

        if (
            not answer_sudo.test_entry
            and not survey_sudo._has_attempts_left(
                answer_sudo.partner_id,
                answer_sudo.email,
                answer_sudo.invite_token
            )
        ):
            return {'error': 'unauthorized'}

        # ---------------------------------------------------------
        # 3. Time limit validation
        # ---------------------------------------------------------

        if (
            answer_sudo.survey_time_limit_reached
            or answer_sudo.question_time_limit_reached
        ):
            return {'error': 'unauthorized'}

        # ---------------------------------------------------------
        # 4. Prepare and save survey answers
        # ---------------------------------------------------------

        errors = {}

        for question in questions:

            inactive_questions = (
                request.env['survey.question']
                if answer_sudo.is_session_answer
                else answer_sudo._get_inactive_conditional_questions()
            )

            if question in inactive_questions:
                continue

            answer, comment = self._extract_comment_from_answers(
                question,
                post.get(str(question.id))
            )

            errors.update(
                question.validate_question(
                    answer,
                    comment
                )
            )

            if not errors.get(question.id):
                answer_sudo.save_lines(
                    question,
                    answer,
                    comment
                )

        # Standard Odoo validation errors.
        if errors and not (
            answer_sudo.survey_time_limit_reached
            or answer_sudo.question_time_limit_reached
        ):
            return {
                'error': 'validation',
                'fields': errors
            }

        # ---------------------------------------------------------
        # 5. Clear inactive conditional answers
        # ---------------------------------------------------------

        if not answer_sudo.is_session_answer:
            answer_sudo._clear_inactive_conditional_answers()

        # ---------------------------------------------------------
        # 6. CUSTOM VALIDATION
        # ---------------------------------------------------------
        #
        # IMPORTANT CHANGE:
        # We no longer wait for the survey's final page to run this
        # check. Instead, we run it as soon as the page that was just
        # submitted contains the Email Question and/or the Phone
        # Question. `questions` here holds only the question(s) that
        # belong to the page just submitted, so this correctly limits
        # the check to the right moment - right after the applicant
        # fills in their email/phone and clicks Submit/Next on that
        # specific page.
        #
        # This also means the error is guaranteed to be shown on a
        # field that IS visible on the current page (no more crashes
        # from trying to scroll to a question on a page that already
        # scrolled past).
        #

        email_question = survey_sudo.email_question_id
        phone_question = survey_sudo.phone_question_id

        current_page_question_ids = questions.ids

        should_check_duplicate = (
            not answer_sudo.test_entry
            and (
                (
                    email_question
                    and email_question.id in current_page_question_ids
                )
                or (
                    phone_question
                    and phone_question.id in current_page_question_ids
                )
            )
        )

        if should_check_duplicate:

            try:
                answer_sudo._check_duplicate_submission()

            except ValidationError as error:

                # _check_duplicate_submission() attaches a
                # `question_id` attribute on the exception instance,
                # telling us exactly which question the error belongs
                # to (email question for duplicate email, phone
                # question for phone format / duplicate phone).
                error_question_id = (
                    getattr(error, 'question_id', False)
                    or (phone_question.id if phone_question else False)
                )

                # Safety net: if the tagged question somehow isn't
                # part of the current page, fall back to the last
                # visible question on this page instead, so the
                # frontend always has a valid element to attach the
                # error message to.
                if error_question_id not in current_page_question_ids:
                    error_question_id = (
                        questions[-1].id
                        if questions
                        else error_question_id
                    )

                return {
                    'error': 'validation',
                    'fields': {
                        str(error_question_id): str(error)
                    }
                }

        # ---------------------------------------------------------
        # 7. Determine if this is the final submission
        # ---------------------------------------------------------

        is_final_submission = (
            answer_sudo.survey_time_limit_reached
            or survey_sudo.questions_layout == 'one_page'
        )

        # Pre-compute the next page/question for the normal flow, so
        # a missing next page is also treated as a final submission.
        # This covers the default "one question/page at a time"
        # layout, where the survey has no explicit 'one_page' flag.
        next_page = False

        if (
            not is_final_submission
            and 'previous_page_id' not in post
            and not answer_sudo.is_session_answer
        ):
            next_page = survey_sudo._get_next_page_or_question(
                answer_sudo,
                page_or_question_id
            )

            if not next_page:
                is_final_submission = True

        # ---------------------------------------------------------
        # 8. Mark survey as done
        # ---------------------------------------------------------

        if is_final_submission:

            answer_sudo._mark_done()

        elif 'previous_page_id' in post:

            answer_sudo.write({
                'last_displayed_page_id': post['previous_page_id']
            })

            return self._prepare_question_html(
                survey_sudo,
                answer_sudo,
                **post
            )

        else:

            # next_page was already computed above in step 7,
            # so we reuse it here instead of calling
            # _get_next_page_or_question() a second time.
            if not answer_sudo.is_session_answer and not next_page:
                answer_sudo._mark_done()

            answer_sudo.write({
                'last_displayed_page_id': page_or_question_id
            })

        return self._prepare_question_html(
            survey_sudo,
            answer_sudo
        )