from career_agent.domain.candidate import SkillItem
from career_agent.domain.fields import ProfileField, VerificationStatus
from career_agent.services.job_requirements import (
    JobRequirements,
    RequirementPriority,
    SkillRequirement,
)
from career_agent.services.job_skill_matcher import (
    SkillMatchStatus,
    match_job_skills,
)
from career_agent.services.skill_relationships import (
    SkillRelationshipType,
    find_related_skill_evidence,
)


def make_skill(
    name: str,
    *,
    level: str = "intermediate",
    proficiency_status: VerificationStatus = VerificationStatus.CONFIRMED,
    commercial: bool = True,
) -> SkillItem:
    return SkillItem(
        name=name,
        category="testing",
        proficiency=ProfileField[str](
            value=level,
            status=proficiency_status,
        ),
        commercial_experience=ProfileField[bool](
            value=commercial,
            status=VerificationStatus.CONFIRMED,
        ),
    )


def make_requirements() -> JobRequirements:
    return JobRequirements(
        required_skills=[
            SkillRequirement(
                name="API testing",
                priority=RequirementPriority.REQUIRED,
            ),
        ],
        preferred_skills=[
            SkillRequirement(
                name="AI familiarity",
                priority=RequirementPriority.PREFERRED,
            ),
        ],
        unspecified_skills=[
            SkillRequirement(
                name="Test cases and test plans",
                priority=RequirementPriority.UNSPECIFIED,
            ),
        ],
    )


def test_related_evidence_finds_configured_relationships() -> None:
    requirements = make_requirements()
    skills = [
        make_skill("API testing"),
        make_skill("Postman"),
        make_skill("AI-assisted testing"),
        make_skill("Test case design and execution"),
    ]

    results = find_related_skill_evidence(requirements, skills)

    relationships = {
        item.requirement: item
        for item in results
    }

    assert set(relationships) == {
        "API testing",
        "AI familiarity",
        "Test cases and test plans",
    }
    assert (
        relationships["API testing"].relationship_type
        is SkillRelationshipType.SUPPORTING_EVIDENCE
    )
    assert (
        relationships["AI familiarity"].relationship_type
        is SkillRelationshipType.SUPPORTING_EVIDENCE
    )
    assert (
        relationships["Test cases and test plans"].relationship_type
        is SkillRelationshipType.PARTIAL_OVERLAP
    )


def test_related_evidence_never_counts_as_an_exact_skill_match() -> None:
    results = find_related_skill_evidence(
        make_requirements(),
        [
            make_skill("Postman"),
            make_skill("AI-assisted testing"),
            make_skill("Test case design and execution"),
        ],
    )

    assert results
    assert all(not item.counts_as_skill_match for item in results)


def test_related_evidence_does_not_change_exact_skill_matching() -> None:
    requirements = make_requirements()
    skills = [
        make_skill("API testing"),
        make_skill("Postman"),
    ]

    exact_matches = match_job_skills(requirements, skills)
    related = find_related_skill_evidence(requirements, skills)

    assert exact_matches.required_skills[0].status is SkillMatchStatus.CONFIRMED
    assert len(related) == 1
    assert related[0].candidate_skill == "Postman"
    assert related[0].counts_as_skill_match is False


def test_unconfirmed_related_skill_remains_unconfirmed() -> None:
    results = find_related_skill_evidence(
        make_requirements(),
        [
            make_skill(
                "Test case design and execution",
                proficiency_status=VerificationStatus.IMPORTED_FROM_CV,
            )
        ],
    )

    assert len(results) == 1
    assert results[0].profile_status is SkillMatchStatus.IMPORTED_FROM_CV
    assert (
        results[0].proficiency_status
        is VerificationStatus.IMPORTED_FROM_CV
    )


def test_no_related_evidence_is_created_for_absent_profile_skills() -> None:
    results = find_related_skill_evidence(
        make_requirements(),
        [make_skill("Postman")],
    )

    assert len(results) == 1
    assert results[0].requirement == "API testing"


def test_relationships_are_only_checked_for_extracted_requirements() -> None:
    requirements = JobRequirements()
    skills = [
        make_skill("Postman"),
        make_skill("AI-assisted testing"),
        make_skill("Test case design and execution"),
    ]

    results = find_related_skill_evidence(requirements, skills)

    assert results == []
