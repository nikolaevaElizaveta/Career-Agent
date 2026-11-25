import pytest

from career_agent.services.job_description import clean_job_description


def test_clean_html_preserves_headings_and_list_items() -> None:
    html = """
    <h2>Responsibilities</h2>
    <ul>
        <li>Write <strong>API</strong> tests</li>
        <li>Prepare test data</li>
    </ul>
    """

    result = clean_job_description(html)

    assert result == (
        "Responsibilities\n"
        "• Write API tests\n"
        "• Prepare test data"
    )


def test_clean_html_preserves_paragraphs() -> None:
    html = "<p>First paragraph</p><p>Second paragraph</p>"

    result = clean_job_description(html)

    assert result == "First paragraph\nSecond paragraph"


def test_clean_html_decodes_entities() -> None:
    html = "QA &amp; Testing&nbsp;Engineer"

    result = clean_job_description(html)

    assert result == "QA & Testing Engineer"


def test_clean_html_removes_script_and_style_content() -> None:
    html = """
    <p>Visible text</p>
    <script>alert("secret")</script>
    <style>.hidden { display: none }</style>
    <p>Another visible paragraph</p>
    """

    result = clean_job_description(html)

    assert result == "Visible text\nAnother visible paragraph"
    assert "alert" not in result
    assert "display: none" not in result


def test_clean_html_collapses_excessive_whitespace() -> None:
    html = "<p>  API   testing   </p><p>\n   SQL \t checks </p>"

    result = clean_job_description(html)

    assert result == "API testing\nSQL checks"


def test_plain_text_is_preserved() -> None:
    text = "Use Postman and SQL for API testing."

    assert clean_job_description(text) == text


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_description_returns_empty_string(value: str | None) -> None:
    assert clean_job_description(value) == ""


def test_malformed_html_is_handled() -> None:
    html = "<p>First <strong>bold<p>Second paragraph"

    result = clean_job_description(html)

    assert "First bold" in result
    assert "Second paragraph" in result

def test_clean_html_adds_space_after_punctuation_at_tag_boundary() -> None:
    html = "<p>Stability,<strong>compatibility</strong> and interaction</p>"

    result = clean_job_description(html)

    assert result == "Stability, compatibility and interaction"


def test_clean_html_separates_adjacent_words_across_inline_tags() -> None:
    html = "<p>Quality<strong>assurance</strong></p>"

    result = clean_job_description(html)

    assert result == "Quality assurance"


def test_clean_html_removes_empty_list_items() -> None:
    html = "<ul><li></li><li>Useful requirement</li></ul>"

    result = clean_job_description(html)

    assert result == "• Useful requirement"
    assert result != "•\n• Useful requirement"