from career_agent.services.job_requirements import (
    RequirementPriority,
    extract_job_requirements,
)


def names(items) -> set[str]:
    return {item.name for item in items}


BANCO_DESCRIPTION = """
<h3>Challenges that await you:</h3>
<ul>
<li>Analyzing requirements, creating test scenarios, preparing test data</li>
<li>Developing and maintaining test documentation</li>
<li>Acceptance and regression testing (automated and manual)</li>
<li>Writing and maintaining automated tests in Go</li>
<li>Identifying and reporting defects</li>
</ul>
<h3>What makes you a great fit:</h3>
<ul>
<li>1–2 years of experience in QA</li>
<li>Programming experience in Go / Java / Python</li>
<li>Experience with Git or other version control systems</li>
<li>Experience developing and maintaining test documentation</li>
</ul>
<h3>Your bonus skills:</h3>
<ul>
<li>Hands-on experience in writing automated tests</li>
<li>Experience with SQL</li>
<li>Experience with AI tools in testing</li>
</ul>
"""


BINANCE_ACCELERATOR_DESCRIPTION = """
<h3>About Binance Accelerator Program</h3>
<p>A 6-month program for Early Career Talent.</p>
<h3>Who may apply</h3>
<p>Current university students and recent graduates</p>
<h3>Responsibilities:</h3>
<ul>
<li>Participate in Binance APP testing across Android and iOS platforms.</li>
<li>Design and execute test cases.</li>
<li>Execute functional and regression testing.</li>
</ul>
<h3>Requirements:</h3>
<ul>
<li>Undergraduate or postgraduate in Computer Science or a related field</li>
<li>Familiar with Java and MySQL</li>
<li>Familiarity with AI is a plus</li>
</ul>
"""


BINANCE_WEB_APP_DESCRIPTION = """
<h3>Role Overview</h3>
<p>Cross-platform quality assurance for Web and App products.</p>
<h3>Key Responsibilities</h3>
<ul>
<li>Design and maintain Web/App test cases and test plans.</li>
<li>Develop and maintain UI/API automated tests using Java, Python, or JavaScript.</li>
<li>Combine automation and manual exploratory testing.</li>
</ul>
<h3>Requirements</h3>
<ul>
<li>Strong coding ability in at least one of Java, Python, or JavaScript
(live coding assessment required)</li>
<li>Extensive Web/App automation testing experience with tools such as
Selenium, Appium, Playwright, etc.</li>
<li>Proficiency in SQL</li>
<li>Familiarity with Web front-end technologies (HTML/CSS/JS) and
mobile platform fundamentals (Android/iOS architecture and characteristics)</li>
</ul>
<h3>Ideal Candidate Profile</h3>
<h4>Background:</h4>
<ul>
<li>1–5 years of QA or test development experience, including at least
1 year of Web or App automation testing</li>
</ul>
"""


def test_banco_plata_separates_individual_skills_and_alternatives() -> None:
    result = extract_job_requirements(BANCO_DESCRIPTION)

    required = names(result.required_skills)
    preferred = names(result.preferred_skills)

    assert {"Git", "Test documentation"} <= required
    assert {"SQL", "Test automation", "AI-assisted testing"} <= preferred
    assert not {"Go", "Java", "Python"} & required

    groups = [
        group
        for group in result.alternative_skill_groups
        if set(group.skills) == {"Go", "Java", "Python"}
    ]
    assert len(groups) == 1
    assert groups[0].match_rule == "any_of"
    assert groups[0].priority == RequirementPriority.REQUIRED


def test_banco_plata_extracts_experience_range() -> None:
    result = extract_job_requirements(BANCO_DESCRIPTION)

    assert len(result.experience_requirements) == 1
    experience = result.experience_requirements[0]

    assert experience.min_years == 1
    assert experience.max_years == 2
    assert experience.area == "QA"
    assert experience.priority == RequirementPriority.REQUIRED
    assert "1–2 years of experience in QA" in experience.evidence


def test_banco_plata_extracts_responsibilities() -> None:
    result = extract_job_requirements(BANCO_DESCRIPTION)

    assert any(
        "Analyzing requirements" in item
        for item in result.responsibilities
    )
    assert any(
        "Writing and maintaining automated tests in Go" in item
        for item in result.responsibilities
    )


def test_banco_plata_keeps_evidence_for_git() -> None:
    result = extract_job_requirements(BANCO_DESCRIPTION)
    git = next(item for item in result.required_skills if item.name == "Git")

    assert git.evidence == [
        "Experience with Git or other version control systems"
    ]
    assert git.sections == ["required"]


def test_binance_accelerator_extracts_java_and_mysql() -> None:
    result = extract_job_requirements(BINANCE_ACCELERATOR_DESCRIPTION)

    required = names(result.required_skills)
    assert {"Java", "MySQL"} <= required


def test_binance_accelerator_extracts_education_without_false_positive() -> None:
    result = extract_job_requirements(BINANCE_ACCELERATOR_DESCRIPTION)

    assert len(result.education_requirements) == 1
    assert "Undergraduate or postgraduate" in (
        result.education_requirements[0].evidence
    )
    assert not any(
        "Solid understanding" in item.evidence
        for item in result.education_requirements
    )


def test_binance_accelerator_marks_ai_as_preferred() -> None:
    result = extract_job_requirements(BINANCE_ACCELERATOR_DESCRIPTION)

    ai = next(
        item for item in result.preferred_skills
        if item.name == "AI familiarity"
    )
    assert any("is a plus" in evidence for evidence in ai.evidence)


def test_binance_web_app_extracts_individual_required_skills() -> None:
    result = extract_job_requirements(BINANCE_WEB_APP_DESCRIPTION)

    required = names(result.required_skills)

    assert {
        "SQL",
        "HTML",
        "CSS",
        "Android",
        "iOS",
        "Test automation",
    } <= required

    # Java and Python are alternatives here.
    # JavaScript is also mentioned separately in HTML/CSS/JS.
    assert "Java" not in required
    assert "Python" not in required
    assert "JavaScript" in required


def test_binance_web_app_extracts_alternative_groups() -> None:
    result = extract_job_requirements(BINANCE_WEB_APP_DESCRIPTION)

    groups = [
        group
        for group in result.alternative_skill_groups
        if group.priority == RequirementPriority.REQUIRED
    ]

    language_groups = [
        group for group in groups
        if set(group.skills) == {"Java", "Python", "JavaScript"}
    ]
    assert len(language_groups) == 1
    assert len(language_groups[0].evidence) == 2
    assert set(language_groups[0].sections) == {
        "responsibilities",
        "required",
    }
    assert any(
        set(group.skills) == {"Selenium", "Appium", "Playwright"}
        for group in groups
    )


def test_binance_web_app_extracts_two_experience_requirements() -> None:
    result = extract_job_requirements(BINANCE_WEB_APP_DESCRIPTION)

    requirements = {
        (item.min_years, item.max_years, item.area)
        for item in result.experience_requirements
    }

    assert (1, 5, "QA or test development") in requirements
    assert (1, None, "Web or App automation testing") in requirements


def test_skills_in_responsibilities_are_not_marked_required() -> None:
    result = extract_job_requirements(
        "<h3>Responsibilities</h3>"
        "<ul><li>Develop automated tests using Python.</li></ul>"
    )

    assert "Python" in names(result.unspecified_skills)
    assert "Python" not in names(result.required_skills)


def test_repeated_skill_is_merged_with_all_evidence() -> None:
    result = extract_job_requirements(
        "<h3>Requirements</h3><ul><li>Proficiency in SQL.</li></ul>"
        "<h3>Responsibilities</h3>"
        "<ul><li>Use SQL for data validation.</li></ul>"
    )

    sql_items = [
        item
        for group in (
            result.required_skills,
            result.preferred_skills,
            result.unspecified_skills,
        )
        for item in group
        if item.name == "SQL"
    ]

    assert len(sql_items) == 1
    assert sql_items[0].priority == RequirementPriority.REQUIRED
    assert len(sql_items[0].evidence) == 2
    assert sql_items[0].sections == ["required", "responsibilities"]


def test_empty_description_returns_empty_result() -> None:
    result = extract_job_requirements(None)

    assert result.required_skills == []
    assert result.preferred_skills == []
    assert result.unspecified_skills == []
    assert result.alternative_skill_groups == []
    assert result.experience_requirements == []
    assert result.education_requirements == []
    assert result.responsibilities == []

def test_intalent_description_separates_responsibilities_and_profile_sections() -> None:
    description = """
    <h3>Responsibilities</h3>
    <ul>
    <li>Develop and implement comprehensive test strategies and test plans</li>
    <li>Design, develop, and maintain automated test scripts and frameworks</li>
    <li>Perform manual testing for complex and high-priority features</li>
    <li>Identify, document, and track software defects</li>
    <li>Collaborate with development and product teams</li>
    </ul>

    <h3>Candidate Profile</h3>
    <h4>Background</h4>
    <ul>
    <li>Bachelor's Degree in Computer Science or a related field</li>
    <li>Minimum 5+ years of experience in QA testing, including
    at least 2 years in a senior role</li>
    </ul>

    <h4>Skills & Competencies</h4>
    <ul>
    <li>Strong experience in test automation frameworks such as Selenium</li>
    <li>Solid understanding of manual testing methodologies</li>
    </ul>

    <h4>Preferred Experience / Skills</h4>
    <ul>
    <li>Knowledge of API testing tools such as Postman</li>
    <li>Experience in database testing with SQL</li>
    </ul>

    <h3>About us</h3>
    <p>We are a recruitment partner helping candidates find opportunities.</p>
    """

    result = extract_job_requirements(description)

    assert result.responsibilities == [
        "Develop and implement comprehensive test strategies and test plans",
        "Design, develop, and maintain automated test scripts and frameworks",
        "Perform manual testing for complex and high-priority features",
        "Identify, document, and track software defects",
        "Collaborate with development and product teams",
    ]

    required = names(result.required_skills)
    preferred = names(result.preferred_skills)

    assert {"Test automation", "Selenium", "Manual testing"} <= required
    assert {"API testing", "Postman", "SQL"} <= preferred

    assert len(result.education_requirements) == 1
    assert "Bachelor" in result.education_requirements[0].evidence

    assert any(
        item.min_years == 5
        and item.max_years is None
        and item.area == "QA testing"
        for item in result.experience_requirements
    )

    assert any(
        item.min_years == 2
        and item.area == "senior role"
        for item in result.experience_requirements
    )

def test_terms_and_application_sections_are_not_extracted_as_responsibilities() -> None:
    description = (
        "<h2>Responsibilities</h2>"
        "<ul><li>Perform API testing and report defects.</li></ul>"
        "<h2>Terms</h2>"
        "<p>Remote, open to candidates anywhere in the world. "
        "Consulting agreement with equity.</p>"
        "<h2>How to apply</h2>"
        "<p>Apply at careers.example.com. "
        "Every candidate completes an online assessment "
        "and a 48-hour task.</p>"
        "<p>Originally posted on Himalayas</p>"
    )

    result = extract_job_requirements(description)

    assert result.responsibilities == [
        "Perform API testing and report defects."
    ]
