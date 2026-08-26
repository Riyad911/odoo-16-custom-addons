/**
 * Client-side (live) helpers for the public survey form.
 *
 * This script is purely a User Experience helper. It does NOT replace
 * any server-side validation - the real duplicate check and phone
 * format check still happen on the server (see survey_user_input.py
 * and controllers/survey.py). This script only makes the form feel
 * more responsive while the applicant is typing:
 *
 *   1. Email question:
 *      Shows a small inline hint ("looks valid" / "looks invalid")
 *      as soon as the applicant types, using a simple email pattern.
 *
 *   2. Phone question:
 *      Only allows digits to be typed, and blocks any character
 *      beyond the 10th digit. Extra keystrokes simply do nothing.
 *
 * HOW QUESTIONS ARE IDENTIFIED:
 * -------------------------------------------------------------------
 * The Email Question / Phone Question configured on the survey can
 * be ANY question, with ANY title wording the survey admin chose
 * (e.g. "البريد الإلكتروني" or "برجاء إدخال بريدك الإلكتروني").
 * So this script never matches on title text.
 *
 * Instead, it calls a small backend endpoint
 * (/survey_duplicate/config/<survey_token>/<answer_token>) that
 * returns the actual question ids configured as Email Question and
 * Phone Question on the survey, and then locates the matching input
 * fields by their question id in the DOM.
 * -------------------------------------------------------------------
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------
    // Configuration
    // -----------------------------------------------------------------

    // Maximum number of digits allowed in the phone field.
    var PHONE_MAX_LENGTH = 10;

    // Simple email shape check: local@domain.tld using only standard
    // Latin email characters. This deliberately rejects anything
    // outside the normal email character set (Arabic letters, '#',
    // spaces, etc.) - it is only a live hint for the applicant, not
    // a strict RFC validator, and not a replacement for server-side
    // validation.
    var EMAIL_PATTERN =
        /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

    // Marker attribute used to avoid attaching the same listeners
    // twice to the same input (the survey form is reloaded via AJAX
    // between pages, so this script may run more than once).
    var HANDLED_ATTR = 'data-survey-duplicate-handled';

    // Cached config (email/phone question ids) for the survey
    // currently being filled in. Fetched once per survey_token +
    // answer_token pair.
    var cachedConfig = null;
    var cachedConfigKey = null;

    // -----------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------

    /**
     * Read the survey_token and answer_token directly from the
     * survey form's own data attributes.
     *
     * @return {{surveyToken: string, answerToken: string}|null}
     */
    function getSurveyTokens() {
        var form = document.querySelector(
            'form[data-survey-token][data-answer-token]'
        );

        if (!form) {
            return null;
        }

        var surveyToken = form.getAttribute('data-survey-token');
        var answerToken = form.getAttribute('data-answer-token');

        if (!surveyToken || !answerToken) {
            return null;
        }

        return {
            surveyToken: surveyToken,
            answerToken: answerToken
        };
    }

    /**
     * Find the text input belonging to the given question id.
     *
     * The survey form renders each question's input with its
     * `name` attribute set to the question id itself (e.g.
     * name="6" for question id 6), so a direct match is enough.
     *
     * @param {number|string} questionId
     * @return {HTMLInputElement|null}
     */
    function findQuestionInputById(questionId) {
        if (!questionId) {
            return null;
        }

        return document.querySelector(
            'input[name="' + questionId + '"]'
        );
    }

    /**
     * Create (or reuse) a small feedback line right below the given
     * input, used to show the live email format hint.
     *
     * @param {HTMLInputElement} input
     * @return {HTMLElement} The feedback element.
     */
    function getOrCreateFeedbackElement(input) {
        var feedback = input.parentNode.querySelector(
            '.survey_duplicate_email_feedback'
        );

        if (feedback) {
            return feedback;
        }

        feedback = document.createElement('div');
        feedback.className = 'survey_duplicate_email_feedback';
        feedback.style.fontSize = '0.85em';
        feedback.style.marginTop = '4px';

        input.parentNode.insertBefore(feedback, input.nextSibling);

        return feedback;
    }

    // -----------------------------------------------------------------
    // Email question: live format hint
    // -----------------------------------------------------------------

    function setupEmailLiveValidation(emailQuestionId) {
        var input = findQuestionInputById(emailQuestionId);

        if (!input || input.getAttribute(HANDLED_ATTR) === 'email') {
            return;
        }

        input.setAttribute(HANDLED_ATTR, 'email');

        var feedback = getOrCreateFeedbackElement(input);

        input.addEventListener('input', function () {
            var value = input.value.trim();

            if (!value) {
                feedback.textContent = '';
                return;
            }

            if (EMAIL_PATTERN.test(value)) {
                feedback.textContent = 'شكل البريد الإلكتروني يبدو صحيحاً.';
                feedback.style.color = '#2e7d32';
            } else {
                feedback.textContent = 'تأكد من صيغة البريد الإلكتروني.';
                feedback.style.color = '#c62828';
            }
        });
    }

    // -----------------------------------------------------------------
    // Phone question: digits only, max 10 characters
    // -----------------------------------------------------------------

    function setupPhoneLiveValidation(phoneQuestionId) {
        var input = findQuestionInputById(phoneQuestionId);

        if (!input || input.getAttribute(HANDLED_ATTR) === 'phone') {
            return;
        }

        input.setAttribute(HANDLED_ATTR, 'phone');

        // Also set the native maxlength attribute as a first layer
        // of protection (covers paste and most browsers' own limit).
        input.setAttribute('maxlength', String(PHONE_MAX_LENGTH));

        input.addEventListener('input', function () {
            // Strip anything that is not a digit, then cap the
            // length. Extra keystrokes beyond 10 digits simply have
            // no visible effect on the field.
            var digitsOnly = input.value.replace(/[^0-9]/g, '');

            input.value = digitsOnly.slice(0, PHONE_MAX_LENGTH);
        });
    }

    // -----------------------------------------------------------------
    // Entry point
    // -----------------------------------------------------------------

    /**
     * Attach the live validation handlers using an already-fetched
     * config (email_question_id / phone_question_id).
     *
     * @param {{email_question_id: (number|boolean),
     *          phone_question_id: (number|boolean)}} config
     */
    function attachWithConfig(config) {
        try {
            if (config.email_question_id) {
                setupEmailLiveValidation(config.email_question_id);
            }

            if (config.phone_question_id) {
                setupPhoneLiveValidation(config.phone_question_id);
            }
        } catch (error) {
            // Never let a problem in this helper script break the
            // actual survey submission flow.
            /* eslint-disable no-console */
            console.warn('survey_duplicate live validation: ', error);
            /* eslint-enable no-console */
        }
    }

    /**
     * Entry point run on initial page load and after every AJAX page
     * change inside the survey. Fetches the config once per survey
     * session (cached), then attaches the handlers.
     */
    function attachLiveValidation() {
        var tokens = getSurveyTokens();

        if (!tokens) {
            return;
        }

        var configKey = tokens.surveyToken + '/' + tokens.answerToken;

        if (cachedConfig && cachedConfigKey === configKey) {
            attachWithConfig(cachedConfig);
            return;
        }

        var configUrl =
            '/survey_duplicate/config/' +
            tokens.surveyToken + '/' + tokens.answerToken;

        fetch(configUrl)
            .then(function (response) {
                return response.json();
            })
            .then(function (config) {
                cachedConfig = config;
                cachedConfigKey = configKey;
                attachWithConfig(config);
            })
            .catch(function (error) {
                /* eslint-disable no-console */
                console.warn('survey_duplicate config fetch failed: ', error);
                /* eslint-enable no-console */
            });
    }

    // Run once the page first loads.
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attachLiveValidation);
    } else {
        attachLiveValidation();
    }

    // The survey form is reloaded page by page via AJAX (no full
    // browser reload), so we also watch the page for newly inserted
    // question wrappers and re-attach the handlers when they appear.
    var observer = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
            if (mutations[i].addedNodes.length) {
                attachLiveValidation();
                break;
            }
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

}());