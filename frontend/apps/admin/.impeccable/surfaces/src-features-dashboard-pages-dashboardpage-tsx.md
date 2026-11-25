---
version: 1
slug: 'src-features-dashboard-pages-dashboardpage-tsx'
primary_target: 'src/features/dashboard/pages/DashboardPage.tsx'
related_targets:
  - 'src/features/dashboard/pages/DashboardPage.module.css'
---

# Service connection foundation

Mode: Operate. This extends the existing Admin shell for the approved P1-02 continuation; no visual identity replacement.

THESIS: Let administrators explicitly check the real public API connection and understand the result without implying authentication or backend dependency readiness.

OWN-WORLD: Preserve the current Ant Design light theme, system typography, blue controls, white surfaces, spacing and root ConfigProvider. No new artwork or design system.

STORY: Begin with an honest empty table; the check action starts a bounded request, shows loading, renders confirmed success, or shows a safe failure and retry. Development preview is labeled and excluded from production.

FIRST VIEWPORT: Existing application heading, service connection heading, scope explanation, check action and two-column result table. The action stays visible on small screens; text wraps without horizontal page overflow.

FORM: Pinned by the approved task to complete the existing frontend foundation using the established Ant Design style and a basic table; seed: none (pinned). No additional navigation or business data management.

Verification and deferred authentication/authorization work are recorded in docs/plan/V1.0-MVP/implementation/P1-02.md. Screenshots remain local working evidence. This extension preserves existing design files and does not create a new visual world.
