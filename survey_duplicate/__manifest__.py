{
    'name': 'Survey Duplicate Submission Prevention',
    'version': '16.0.1.0.0',
    'category': 'Surveys',
    'summary': 'Prevent duplicate survey submissions using email and phone',

    'description': """
        Prevent duplicate submissions for public surveys.

        Each survey can be configured with:
        - An Email Question
        - A Phone Question

        The module validates:
        - Phone number format.
        - Duplicate email submissions.
        - Duplicate phone submissions.
    """,

    'author': 'Riyad Alkabbani',

    'depends': [
        'survey',
    ],

    'data': [
        'views/survey_views.xml',
    ],

    'assets': {
        'web.assets_frontend': [
            'survey_duplicate/static/src/js/survey_duplicate_validation.js',
    ],
    },
    'installable': True,
    'application': False,
}