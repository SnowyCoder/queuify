from crispy_forms.layout import Div, HTML, Submit


def crispy_save_or_go_back(save_text='Save!'):
    return Div(
        HTML('<button type="button" class="btn btn-secondary" onclick="history.back()">Back</button>'),
        Submit(save_text, save_text),
        css_class="btn-group"
    )
