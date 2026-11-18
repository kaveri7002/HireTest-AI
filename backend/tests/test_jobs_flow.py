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
        "Internship",
    )
    expect(page.get_by_role("status")).to_contain_text("Job posted successfully.")

    auth.sign_out()
    auth.register("Portal Student", "student@e2e.test", "StrongPassword123", "student")
    jobs.open()
    demo_job = page.locator(".job-card").filter(has_text="DEMO ONLY").first
    expect(demo_job.get_by_role("button", name="Sample only")).to_be_disabled()
    page.get_by_label("Filter by job type").select_option(label="Full time")
    expect(page.get_by_role("heading", name="Playwright QA Engineer")).not_to_be_visible()
    page.get_by_label("Filter by job type").select_option(label="Internship")
    job_card = page.locator(".job-card").filter(has=page.get_by_role("heading", name="Playwright QA Engineer"))
    expect(job_card).to_be_visible()
    job_card.get_by_role("button", name="Save Playwright QA Engineer").click()
    page.get_by_role("button", name="Saved (1)").click()
    expect(page.get_by_role("heading", name="Saved jobs")).to_be_visible()
    expect(job_card).to_be_visible()
    page.get_by_role("button", name="Saved (1)").click()

    page.get_by_role("button", name="Test cases", exact=True).click()
    page.get_by_role("button", name="Approve").first.click()
    expect(page.get_by_role("button", name="Approved").first).to_be_visible()
    page.get_by_role("button", name="Edit Matching search returns results").click()
    page.get_by_label("Title").fill("Updated search example")
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_role("heading", name="Updated search example")).to_be_visible()

    jobs.open()
    jobs.apply_for("Playwright QA Engineer")
    expect(page.get_by_role("status")).to_contain_text("Your application was submitted.")

    expect(page.get_by_role("button", name="Applied · submitted")).to_be_disabled()
    expect(page.get_by_role("heading", name="My applications")).to_be_visible()

    auth.sign_out()
    auth.sign_in("recruiter@e2e.test", "StrongPassword123")
    jobs.open()
    jobs.review_applicants("Playwright QA Engineer", "Portal Student", "shortlisted")
