---
version: 1
slug: 'src-features-auth-pages-loginpage-tsx'
primary_target: 'src/features/auth/pages/LoginPage.tsx'
related_targets: []
---

# Login entry

Mode: Operate. Audience: employees entering Chat and administrators entering Admin. The task is to identify the correct login method, understand availability, and enter the authorized application when a trusted session exists. This P1-02 slice provides the interface and controlled state; live authentication awaits P1-03/P1-04.

## Direction contract

THESIS: A clear enterprise access gate with one primary login action and an honest availability message. Authentication success comes from a trusted platform session.

OWN-WORLD: Inherit the current Ant Design light theme, system typography, blue primary controls, white surfaces and restrained spacing. No new brand assets or decorative imagery.

STORY: Chat offers enterprise identity login; Admin offers labeled username/password fields. Loading, failed and denied access remain recoverable. Development Chat preview is labeled and excluded from production.

FIRST VIEWPORT: EnterpriseRag brand header, centered readable form, prominent heading, instructions, login action and status message. Mobile retains the full action and field labels without horizontal scrolling.

FORM: Conventional enterprise login form, fixed by the approved P1-02 continuation. seed: none (pinned); "页面沿用现有 Ant Design 风格". Code-led extension of the existing application system.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

No visual-world replacement or shipping rasters. Existing code is the visual authority; implementation and verification are recorded in P1-02.md. The existing absence of DESIGN.md is not repaired as part of this extension.
