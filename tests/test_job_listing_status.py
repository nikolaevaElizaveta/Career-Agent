from datetime import UTC, datetime, timedelta

from career_agent.domain.job_posting import JobPosting, ListingStatus

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def make_job(expires_at=None) -> JobPosting:
    return JobPosting(
        id="test-job",
        source="himalayas",
        source_job_id="test-job",
        title="QA Engineer",
        company="Example Ltd",
        discovered_at=NOW,
        expires_at=expires_at,
    )


def test_listing_status_is_within_provider_period() -> None:
    job = make_job(NOW + timedelta(days=1))

    assert job.listing_status(NOW) is ListingStatus.WITHIN_LISTED_PERIOD


def test_listing_status_is_expired_at_expiry_instant() -> None:
    job = make_job(NOW)

    assert job.listing_status(NOW) is ListingStatus.EXPIRED


def test_listing_status_is_unknown_without_expiry_date() -> None:
    job = make_job()

    assert job.listing_status(NOW) is ListingStatus.UNKNOWN


def test_listing_status_handles_naive_database_datetime() -> None:
    job = make_job(datetime(2026, 11, 24, 12, 0))

    assert job.listing_status(NOW) is ListingStatus.WITHIN_LISTED_PERIOD
