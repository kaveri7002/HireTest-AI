from playwright.sync_api import expect

from backend.tests.pages.auth_page import AuthPage
from backend.tests.pages.jobs_page import JobsPage


def test_recruiter_posts_and_student_applies_to_a_job(page, live_server):
    page.goto(live_server)
    auth = AuthPage(page)
    jobs = JobsPage(page)

    auth.register("Portal Recruiter", "recruiter@e2e.test", "StrongPassword123", "recruiter")
    jobs.open()
    jobs.create_job(
        "Playwright QA Engineer",
        "HireTest Demo",
        "Remote",
        "Validate job portal workflows with browser tests.",
    )
    expect(page.get_by_role("status")).to_contain_text("Job posted successfully.")

    auth.sign_out()
    auth.register("Portal Student", "student@e2e.test", "StrongPassword123", "student")
    jobs.open()
    jobs.apply_for("Playwright QA Engineer")
    expect(page.get_by_role("status")).to_contain_text("Your application was submitted.")

    expect(page.get_by_role("button", name="Applied · submitted")).to_be_disabled()
    expect(page.get_by_role("heading", name="My applications")).to_be_visible()

    auth.sign_out()
    auth.sign_in("recruiter@e2e.test", "StrongPassword123")
    jobs.open()
    jobs.review_applicants("Playwright QA Engineer", "Portal Student", "shortlisted")
