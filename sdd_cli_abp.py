#!/usr/bin/env python3
"""
SDD CLI — Spec-Driven Development for Angular + ABP Framework (.NET)
Optimized for ABP layered architecture, DDD patterns, and Angular frontend.
Run: python sdd_cli_abp.py
"""

import os
import sys
import json
import datetime
from pathlib import Path
from openai import OpenAI

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.syntax import Syntax
from rich import print as rprint
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.rule import Rule
from rich.columns import Columns

# ─── Config ─────────────────────────────────────────────────────────────────────

LMSTUDIO_BASE_URL    = "http://localhost:1234/v1"
MODEL_NAME           = "qwen3.5-4b-claude-4.6-opus-reasoning-distilled"   # adjust to match your LM Studio model name
SPECS_DIR            = Path("./specs")
PROJECT_CONTEXT_FILE = Path("./sdd_project.json")
SPECS_DIR.mkdir(exist_ok=True)

# ABP Framework defaults
ABP_DEFAULTS = {
    "dotnet_version":     "8.0",
    "abp_version":        "8.x",
    "angular_version":    "17+",
    "db_provider":        "Entity Framework Core (SQL Server)",
    "auth":               "OpenIddict (ABP default)",
    "localization":       "ABP Localization (JSON resources)",
    "ui_theme":           "LeptonX Lite",
    "test_framework_be":  "xUnit + NSubstitute + Shouldly",
    "test_framework_fe":  "Jest + Angular Testing Library",
}

# Project-level context defaults (overridden by sdd_project.json when present)
_DEFAULT_PROJECT_CONTEXT: dict = {
    "project_name":    "Acme.BookStore",
    "namespace":       "Acme.BookStore",
    "abp_version":     ABP_DEFAULTS["abp_version"],
    "dotnet_version":  ABP_DEFAULTS["dotnet_version"],
    "angular_version": ABP_DEFAULTS["angular_version"],
    "db_provider":     ABP_DEFAULTS["db_provider"],
    "auth":            ABP_DEFAULTS["auth"],
    "multi_tenant":    "Yes",
    "default_roles":   "Admin, Manager, Viewer",
    "table_prefix":    "App",
    "description":     "",
}

client  = OpenAI(base_url=LMSTUDIO_BASE_URL, api_key="lm-studio")
console = Console()


# ─── Project Context helpers ────────────────────────────────────────────────────

def load_project_context() -> dict:
    """Load sdd_project.json; fall back to built-in defaults."""
    if PROJECT_CONTEXT_FILE.exists():
        try:
            data = json.loads(PROJECT_CONTEXT_FILE.read_text(encoding="utf-8"))
            # Merge so new keys added in future versions are present
            merged = dict(_DEFAULT_PROJECT_CONTEXT)
            merged.update(data)
            return merged
        except Exception:
            pass
    return dict(_DEFAULT_PROJECT_CONTEXT)


def save_project_context(ctx: dict) -> None:
    PROJECT_CONTEXT_FILE.write_text(json.dumps(ctx, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]✔ Project context saved →[/green] [dim]{PROJECT_CONTEXT_FILE.resolve()}[/dim]\n")

# ─── ABP Layer Reference ────────────────────────────────────────────────────────

ABP_LAYERS = """
ABP Framework Layered Architecture Reference:
  Domain Layer         → Entities, Value Objects, Domain Events, Domain Services, Repository Interfaces
  Application Layer    → AppServices (IApplicationService), DTOs, AutoMapper Profiles, Validators (FluentValidation)
  HTTP API Layer       → Controllers (AbpController / inherits from ApplicationService), API versioning
  EntityFrameworkCore  → DbContext (inherits AbpDbContext), Migrations, EF Configurations
  Angular Frontend     → Modules (NgModule / standalone), Components, Services (RestService / ABP proxy), Routing, Permissions
  Shared Contracts     → IRemoteService DTOs, Permissions (PermissionDefinitionProvider), Localization keys
"""

ABP_CONVENTIONS = """
ABP Key Conventions:
  - Entities inherit from AggregateRoot<TKey> or Entity<TKey> or FullAuditedAggregateRoot<TKey>
  - Application Services implement CRUD via CrudAppService<TEntity, TGetDto, TKey, TListInput, TCreateUpdateDto>
  - Permission names: [ProjectName].[Module].[Action] (e.g., BookStore.Books.Create)
  - DTO naming: [Entity]Dto (read), Create[Entity]Dto, Update[Entity]Dto, [Entity]ListFilterDto
  - Angular services use ABP RestService or generated proxies via `abp generate-proxy`
  - Feature flags via IFeatureChecker
  - Settings via ISettingProvider / SettingDefinitionProvider
  - Multi-tenancy via IMultiTenant / HasTenantId
  - Audit logging via FullAuditedEntity or IAuditedObject
  - Repository: IRepository<TEntity, TKey> — use async with CancellationToken
"""

# ─── Prompts ────────────────────────────────────────────────────────────────────

PROMPTS = {
    # ── 1. Discovery ──────────────────────────────────────────────────────────
    "discovery": {
        "system": (
            "You are a senior product analyst specializing in ABP Framework (.NET) and Angular projects. "
            "Translate vague stakeholder input into structured problem statements aligned with ABP's "
            "module system, DDD patterns, and Angular SPA architecture. Be rigorous and never invent requirements.\n\n"
            f"{ABP_LAYERS}\n"
            "Produce output with these exact markdown sections:\n"
            "## Problem Statement\n## Confirmed Requirements\n## ABP Module Scope\n"
            "## Open Questions\n## Suggested Success Metrics\n## Risks & Dependencies"
        ),
        "user_template": (
            "Analyze the following raw input and produce a structured discovery report "
            "for an ABP Framework + Angular application.\n\n"
            "Feature Request / Stakeholder Notes:\n\"\"\"\n{input}\n\"\"\"\n\n"
            "Rules:\n"
            "- Do not invent requirements not present in the input\n"
            "- Flag contradictions explicitly\n"
            "- Keep Problem Statement to 3 sentences max\n"
            "- Under 'ABP Module Scope': suggest which ABP layer(s) are affected and whether this needs a new ABP module\n"
            "- Phrase Open Questions as direct questions to ask a stakeholder\n"
            "- Mention any ABP built-in features that may satisfy requirements (e.g., Audit Logging, Permission System)"
        ),
    },

    # ── 2. Domain / Entity Design ─────────────────────────────────────────────
    "domain": {
        "system": (
            "You are a DDD expert and ABP Framework architect. Design the domain layer for an ABP module "
            "following ABP conventions strictly. Every output must be implementable without modification.\n\n"
            f"{ABP_LAYERS}\n{ABP_CONVENTIONS}\n"
            "Produce output with these exact markdown sections:\n"
            "## Aggregate Roots & Entities\n## Value Objects\n## Domain Events\n"
            "## Repository Interfaces\n## Domain Service Interfaces\n"
            "## Business Rule Validations\n## EF Core Configuration Notes"
        ),
        "user_template": (
            "Design the domain layer for the following ABP module.\n\n"
            "**Module Name:** {module_name}\n"
            "**Namespace:** {namespace}\n"
            "**Description:** {description}\n"
            "**Multi-tenant:** {multi_tenant}\n"
            "**Soft Delete Required:** {soft_delete}\n"
            "**Audit Fields:** {audit_fields}\n\n"
            "Rules:\n"
            "- All entities must specify base class (e.g., FullAuditedAggregateRoot<Guid>)\n"
            "- List all properties with C# type, required/optional, max length constants (e.g., MaxNameLength = 128)\n"
            "- Domain events must extend EtoBase or follow ABP event pattern\n"
            "- Repository interfaces must extend IRepository<TEntity, TKey>\n"
            "- Include a Consts class (e.g., BookConsts) for all string length constraints\n"
            "- Note any indexes or unique constraints needed"
        ),
    },

    # ── 3. Application Service Spec ───────────────────────────────────────────
    "appservice": {
        "system": (
            "You are an ABP Framework application-layer architect. Design complete application service "
            "specifications including all DTOs, validators, AutoMapper profiles, and permission checks.\n\n"
            f"{ABP_LAYERS}\n{ABP_CONVENTIONS}\n"
            "Produce output with these exact markdown sections:\n"
            "## Application Service Interface\n## DTOs (with properties & validation rules)\n"
            "## AutoMapper Profile\n## Permission Requirements\n## Business Logic Rules\n"
            "## Acceptance Criteria\n## Error Scenarios"
        ),
        "user_template": (
            "Design the application service spec for:\n\n"
            "**Story ID:** {story_id}\n"
            "**Module:** {module_name}\n"
            "**Namespace:** {namespace}\n"
            "**Service Purpose:** {purpose}\n"
            "**CRUD Operations Required:** {crud_ops}\n"
            "**Permission Prefix:** {permission_prefix}\n"
            "**Additional Business Rules:** {business_rules}\n\n"
            "Rules:\n"
            "- Interface must extend IApplicationService\n"
            "- Every method must list: return type, input DTO, permission policy required\n"
            "- DTOs: specify which fields are required vs optional, include FluentValidation rules\n"
            "- Criterion IDs: AC-{story_id}-001, AC-{story_id}-002 ...\n"
            "- Minimum 5 acceptance criteria, each must be binary pass/fail\n"
            "- Include at least one negative test case (e.g., unauthorized access, not found, duplicate)\n"
            "- Mark each criterion priority: high / medium / low\n"
            "- List all exception types to throw (e.g., BusinessException, EntityNotFoundException)"
        ),
    },

    # ── 4. HTTP API / Controller Spec ─────────────────────────────────────────
    "api": {
        "system": (
            "You are an ABP Framework HTTP API layer architect. Specify REST endpoints following ABP "
            "conventions, versioning, Swagger documentation requirements, and ABP dynamic API client generation.\n\n"
            f"{ABP_LAYERS}\n"
            "Produce output with these exact markdown sections:\n"
            "## API Endpoints Table\n## Route Conventions\n## Request / Response Schemas\n"
            "## Authorization Policies\n## Validation Rules\n## Swagger / OpenAPI Notes\n"
            "## ABP Dynamic Client Proxy Notes"
        ),
        "user_template": (
            "Specify the HTTP API layer for:\n\n"
            "**Story ID:** {story_id}\n"
            "**Module:** {module_name}\n"
            "**Base Route:** /api/{route_prefix}\n"
            "**API Version:** {api_version}\n"
            "**Application Service:** {app_service}\n"
            "**Authentication Required:** {auth_required}\n\n"
            "Rules:\n"
            "- Table columns: Method | Route | Permission | Request DTO | Response DTO | Status Codes\n"
            "- All routes must follow ABP REST conventions (GET list = PagedResultDto, GET single, POST, PUT, DELETE)\n"
            "- Specify any custom routes that deviate from CRUD pattern\n"
            "- List all HTTP status codes each endpoint can return (200, 201, 400, 401, 403, 404, 409, 422, 500)\n"
            "- Note which endpoints require tenant header (X-Tenant-Id)\n"
            "- ABP Dynamic Client Proxy: confirm if controller inherits AbpController or exposes IApplicationService directly"
        ),
    },

    # ── 5. Angular Component / Module Spec ────────────────────────────────────
    "angular": {
        "system": (
            "You are a senior Angular architect specializing in ABP Framework Angular UI. "
            "Specify Angular modules, components, and services following ABP Angular conventions "
            "including ABP permission directives, lazy-loaded feature modules, and ABP proxy services.\n\n"
            "ABP Angular Key Conventions:\n"
            "  - Feature modules are lazy-loaded via routing\n"
            "  - Use ABP-generated proxy services (abp generate-proxy) for HTTP calls\n"
            "  - Use AbpModule, CoreModule from '@abp/ng.core'\n"
            "  - Permission checks: *abpPermission directive or PermissionService\n"
            "  - Breadcrumbs via ABP breadcrumb service\n"
            "  - Toastr notifications via ToasterService from '@abp/ng.theme.shared'\n"
            "  - Confirmation dialogs via ConfirmationService from '@abp/ng.theme.shared'\n"
            "  - LeptonX table: use ngx-datatable or ABP's list component\n"
            "  - Forms: Reactive Forms with ABP validation helpers\n\n"
            "Produce output with these exact markdown sections:\n"
            "## Module Structure\n## Component Tree\n## Service Layer\n## Routing Definition\n"
            "## State Management\n## Permission Guards\n## Acceptance Criteria\n## Angular Test Plan"
        ),
        "user_template": (
            "Specify the Angular frontend module for:\n\n"
            "**Story ID:** {story_id}\n"
            "**Feature Module Name:** {module_name}\n"
            "**Route Path:** {route_path}\n"
            "**API Proxy Service:** {proxy_service}\n"
            "**Required Permissions:** {permissions}\n"
            "**UI Components Needed:** {ui_components}\n"
            "**State Management Approach:** {state_mgmt}\n\n"
            "Rules:\n"
            "- List every component with: name, type (smart/dumb), inputs, outputs, responsibilities\n"
            "- Services: list methods, return types, which ABP proxy endpoints they wrap\n"
            "- Routes: include canActivate guards and which permission each route requires\n"
            "- Criterion IDs: AC-{story_id}-FE-001 ...\n"
            "- Minimum 5 UI acceptance criteria covering: rendering, CRUD interactions, permission hiding, error states\n"
            "- Test plan: list Jest test cases per component with testing approach (shallow/deep)"
        ),
    },

    # ── 6. Full-Stack Spec (Orchestration) ────────────────────────────────────
    "spec": {
        "system": (
            "You are an expert ABP Framework full-stack architect. Create a comprehensive, testable "
            "specification covering all layers: Domain → Application → HTTP API → Angular UI.\n\n"
            f"{ABP_LAYERS}\n{ABP_CONVENTIONS}\n"
            "Use these markdown sections:\n"
            "## Feature Overview\n## ABP Module Layers Affected\n## Prerequisites & Context\n"
            "## User Flow (Happy Path)\n## Acceptance Criteria (Backend)\n"
            "## Acceptance Criteria (Frontend)\n## Edge Cases & Error Scenarios\n"
            "## Non-Functional Requirements\n## ABP Built-In Features Leveraged\n"
            "## Verification Plan"
        ),
        "user_template": (
            "Generate a complete ABP + Angular SDD specification for:\n\n"
            "**Story ID:** {story_id}\n"
            "**Module:** {module_name}\n"
            "**Namespace:** {namespace}\n"
            "**User Story:** {user_story}\n"
            "**Current State:** {current_state}\n"
            "**NFR Targets:** {nfr}\n"
            "**Multi-Tenant:** {multi_tenant}\n"
            "**ABP Version:** {abp_version}\n\n"
            "Rules:\n"
            "- Backend criterion IDs: AC-{story_id}-BE-001 ...\n"
            "- Frontend criterion IDs: AC-{story_id}-FE-001 ...\n"
            "- Minimum 5 backend + 5 frontend acceptance criteria\n"
            "- Each criterion must be binary (pass/fail)\n"
            "- Include at least one negative test per section (auth failure, validation error, 404)\n"
            "- Mark each priority: high / medium / low\n"
            "- 'ABP Built-In Features Leveraged': list any ABP modules/features used (Audit Log, Blob Storing, etc.)"
        ),
    },

    # ── 7. Permission System Spec ─────────────────────────────────────────────
    "permissions": {
        "system": (
            "You are an ABP Framework security architect. Design the complete permission system "
            "for a module, covering backend policy definitions and Angular UI permission gates.\n\n"
            "ABP Permission Conventions:\n"
            "  - PermissionDefinitionProvider defines groups and permissions\n"
            "  - Permission names: [Project].[Module].[Action] — e.g., Acme.Books.Create\n"
            "  - Use Authorize attribute or policy-based authorization in AppService\n"
            "  - Angular: *abpPermission='\"Acme.Books.Edit\"' structural directive\n"
            "  - Role-based seed data in DataSeeder\n\n"
            "Produce output with these exact markdown sections:\n"
            "## Permission Group Definition\n## Permission List\n"
            "## Role-to-Permission Matrix\n## Backend Authorization Points\n"
            "## Angular UI Permission Gates\n## Data Seeder Requirements"
        ),
        "user_template": (
            "Design the permission spec for:\n\n"
            "**Module:** {module_name}\n"
            "**Project Name:** {project_name}\n"
            "**Operations:** {operations}\n"
            "**Roles in System:** {roles}\n\n"
            "Rules:\n"
            "- Every permission must have: constant name, display name, parent group\n"
            "- Role matrix: rows = roles, columns = permissions, cell = Y/N\n"
            "- Backend: list every AppService method and which permission policy it requires\n"
            "- Angular: list every button/route/section that needs a permission directive or guard\n"
            "- Data seeder: which permissions are granted by default to which roles"
        ),
    },

    # ── 8. EF Core / Database Spec ────────────────────────────────────────────
    "database": {
        "system": (
            "You are an ABP Framework data architect. Specify the EF Core database schema, "
            "migrations strategy, and seed data following ABP DbContext conventions.\n\n"
            "ABP EF Core Conventions:\n"
            "  - DbContext inherits AbpDbContext<TDbContext>\n"
            "  - Table names: use ABP table prefix conventions\n"
            "  - Configure via IEntityTypeConfiguration<TEntity> classes\n"
            "  - Seed data via IDataSeedContributor\n"
            "  - Multi-tenant: RLS via ABP data filter\n"
            "  - Soft delete: ISoftDelete automatically filtered\n\n"
            "Produce output with these exact markdown sections:\n"
            "## Table Definitions\n## Indexes & Unique Constraints\n"
            "## Foreign Keys & Relationships\n## Migration Strategy\n"
            "## Seed Data Requirements\n## Query Performance Notes"
        ),
        "user_template": (
            "Specify the database / EF Core layer for:\n\n"
            "**Module:** {module_name}\n"
            "**DB Provider:** {db_provider}\n"
            "**Table Prefix:** {table_prefix}\n"
            "**Entities:** {entities}\n"
            "**Multi-Tenant Data Isolation:** {multi_tenant}\n\n"
            "Rules:\n"
            "- Table definition: column name | C# type | SQL type | nullable | max length | default\n"
            "- List all indexes (composite if needed) and their purpose\n"
            "- Migration strategy: breaking vs non-breaking changes, rollback plan\n"
            "- Seed data: what must exist for the app to function (e.g., default roles, settings)\n"
            "- Note any columns requiring encryption or masking (GDPR/PII)"
        ),
    },

    # ── 9. Review ─────────────────────────────────────────────────────────────
    "review": {
        "system": (
            "You are a senior QA architect with deep ABP Framework and Angular expertise. "
            "Conduct a spec quality audit focusing on ABP-specific gaps: missing permission checks, "
            "DTOs without validation, multi-tenancy gaps, and untestable Angular UI criteria.\n\n"
            f"{ABP_CONVENTIONS}\n"
            "Output these markdown sections:\n"
            "## Ambiguous Statements\n## Untestable Criteria\n## Missing Edge Cases\n"
            "## ABP-Specific Gaps\n## Angular UI Gaps\n## Non-Functional Gaps\n"
            "## Dependency Risks\n## Overall Score"
        ),
        "user_template": (
            "Review this ABP + Angular specification and produce a structured quality report.\n\n"
            "Specification:\n\"\"\"\n{spec}\n\"\"\"\n\n"
            "Rules:\n"
            "- Be specific — quote directly from the spec when flagging issues\n"
            "- Suggest rewrites, not just problems\n"
            "- Score each dimension 1–5: Completeness, Testability, Clarity, NFR Coverage, "
            "  ABP Convention Compliance, Angular Coverage\n"
            "- Explicitly check: permission definitions complete? DTOs validated? "
            "  multi-tenancy addressed? error codes specified? Angular permission gates listed?\n"
            "- End with: APPROVE / APPROVE WITH CHANGES / REJECT"
        ),
    },

    # ── 10. Backend Tests ─────────────────────────────────────────────────────
    "tests_be": {
        "system": (
            "You are a senior .NET test engineer specializing in ABP Framework. Write xUnit + NSubstitute + "
            "Shouldly test scaffolding that maps 1:1 to acceptance criteria. Follow ABP test project conventions.\n\n"
            "ABP Test Conventions:\n"
            "  - Application tests inherit AbpIntegratedTest<TestModule> or use in-memory db\n"
            "  - Use WithUnitOfWork() for data operations in tests\n"
            "  - Domain tests: unit test with no EF dependency\n"
            "  - Permission tests: use WithUser() to set current user / permissions\n"
            "  - Test project namespaces: [Project].Application.Tests, [Project].Domain.Tests\n"
            "  - Use IRepository directly or mock via NSubstitute\n"
            "  - Shouldly assertions: result.ShouldBe(), result.ShouldNotBeNull(), etc.\n"
        ),
        "user_template": (
            "Generate .NET xUnit test scaffolding for:\n\n"
            "**Story ID:** {story_id}\n"
            "**Layer:** {layer}\n"
            "**Namespace:** {namespace}\n"
            "**Class Under Test:** {class_under_test}\n"
            "**Acceptance Criteria:**\n\"\"\"\n{criteria}\n\"\"\"\n"
            "**Available Mocks / Fixtures:** {mocks}\n\n"
            "Rules:\n"
            "- Class names: [Subject]Tests (e.g., BookAppServiceTests)\n"
            "- Method names: [MethodName]_[Scenario]_[ExpectedResult] (e.g., CreateAsync_WithDuplicateName_ShouldThrowBusinessException)\n"
            "- Use Arrange / Act / Assert with // Arrange, // Act, // Assert comments\n"
            "- Add [Fact] for single-case and [Theory] + [InlineData] for parameterized tests\n"
            "- Each AC must have at least one positive and one negative test\n"
            "- Mark incomplete stubs with // TODO: implement\n"
            "- Never use Assert.True(x != null) — use Shouldly: x.ShouldNotBeNull()"
        ),
    },

    # ── 11. Angular Tests ─────────────────────────────────────────────────────
    "tests_fe": {
        "system": (
            "You are a senior Angular test engineer specializing in ABP Angular UIs. "
            "Write Jest + Angular Testing Library test scaffolding mapping 1:1 to frontend acceptance criteria.\n\n"
            "ABP Angular Test Conventions:\n"
            "  - Use TestBed with ABP modules properly configured or mocked\n"
            "  - Mock ABP proxy services with jest.fn()\n"
            "  - Test permission directives by providing mock PermissionService\n"
            "  - Use screen.getByRole / getByText (Angular Testing Library style)\n"
            "  - For forms: use userEvent.type() for realistic input simulation\n"
            "  - Mock ToasterService and ConfirmationService\n"
        ),
        "user_template": (
            "Generate Angular Jest test scaffolding for:\n\n"
            "**Story ID:** {story_id}\n"
            "**Component / Service:** {component_name}\n"
            "**Module:** {module_name}\n"
            "**Acceptance Criteria:**\n\"\"\"\n{criteria}\n\"\"\"\n"
            "**Mock Services:** {mocks}\n\n"
            "Rules:\n"
            "- describe blocks group by component/feature\n"
            "- Test function names: should_[expected_behaviour]_when_[condition]\n"
            "- Cover: renders correctly, CRUD interactions, permission-hidden elements, error states\n"
            "- Mark incomplete stubs with // TODO\n"
            "- Include at least one negative test per describe block (e.g., button hidden when no permission)\n"
            "- Avoid snapshot tests — test behaviour not markup"
        ),
    },

    # ── 12. Gap Analysis ──────────────────────────────────────────────────────
    "gap": {
        "system": (
            "You are a spec refinement engine for ABP Framework + Angular projects. "
            "Analyze test results against original specs to identify ABP-specific gaps such as "
            "missing permission checks, uncovered tenant scenarios, unhandled ABP exceptions, "
            "and Angular proxy errors.\n\n"
            "Output these sections:\n"
            "## Failing Criteria Analysis\n## New Edge Cases Discovered\n"
            "## ABP-Specific Gaps Found\n## Outdated or Redundant Criteria\n## Spec Changelog"
        ),
        "user_template": (
            "Analyze test run results against the original spec.\n\n"
            "**Original Spec Acceptance Criteria:**\n\"\"\"\n{spec}\n\"\"\"\n\n"
            "**Test Results:**\n\"\"\"\n{results}\n\"\"\"\n\n"
            "**Bug Reports:**\n\"\"\"\n{bugs}\n\"\"\"\n\n"
            "Rules:\n"
            "- Distinguish spec bugs from implementation bugs\n"
            "- Proposed new criteria must follow existing spec format with AC IDs\n"
            "- Flag any ABP-specific failures (permission denied unexpectedly, tenant filter not applied, "
            "  AutoMapper misconfiguration, FluentValidation not triggered)\n"
            "- Changelog date: {date}"
        ),
    },

    # ── 13. Fast Spec ─────────────────────────────────────────────────────────
    "fastspec": {
        "system": (
            "You are a concise ABP Framework + Angular spec writer for small, low-risk features. "
            "Generate lightweight fast-track specifications under 1 page.\n\n"
            "Output these sections:\n"
            "## Overview\n## ABP Layers Touched\n## Acceptance Criteria\n"
            "## Edge Cases\n## Definition of Done"
        ),
        "user_template": (
            "Generate a fast-track ABP + Angular spec for:\n\n"
            "**Feature:** {feature}\n"
            "**Description:** {description}\n"
            "**Layers Affected:** {layers}\n"
            "**Estimated Complexity:** Small (< 3 days)\n\n"
            "Rules:\n"
            "- Overview: 2 sentences max\n"
            "- 'ABP Layers Touched': one-line note per affected layer\n"
            "- Minimum 3, maximum 8 acceptance criteria (mix BE + FE)\n"
            "- Edge cases: bullet list, max 5\n"
            "- Definition of Done checklist must include: unit tests passing, "
            "  permissions defined, Angular proxy regenerated, localization keys added"
        ),
    },

    # ── 14. Localization Spec ─────────────────────────────────────────────────
    "localization": {
        "system": (
            "You are an ABP Framework localization specialist. Specify all localization keys "
            "and resources needed for a feature, following ABP JSON localization conventions.\n\n"
            "ABP Localization Conventions:\n"
            "  - JSON files in [Module]/Localization/[ModuleName] folder\n"
            "  - Default culture: en\n"
            "  - Key naming: PascalCase nouns and sentences (e.g., 'BookName', 'AreYouSure')\n"
            "  - ABP uses L('key') in Razor, this.l('key') in Angular services\n"
            "  - Share keys via AbpValidationResource for common validation messages\n\n"
            "Output these sections:\n"
            "## New Localization Keys\n## Reused ABP Built-in Keys\n"
            "## Cultures Required\n## Angular Pipe Usage Notes"
        ),
        "user_template": (
            "Specify localization requirements for:\n\n"
            "**Module:** {module_name}\n"
            "**Feature:** {feature}\n"
            "**Cultures Required:** {cultures}\n"
            "**UI Text List (raw):** {ui_text}\n\n"
            "Rules:\n"
            "- For each key: Key | English Value | Context/Usage\n"
            "- Identify which ABP built-in keys can be reused (e.g., 'Save', 'Cancel', 'Delete')\n"
            "- Flag any keys that require pluralization rules\n"
            "- Angular: note where {{ 'Key' | abpLocalization }} pipe should be used vs service"
        ),
    },
}

# ─── Core LLM call (streaming) ──────────────────────────────────────────────────

def stream_llm(system: str, user: str, title: str) -> str:
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/bold cyan]", style="cyan"))
    console.print()
    full_response = []
    try:
        stream = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.2,
            max_tokens=4096,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            full_response.append(delta)
            console.print(delta, end="", markup=False)
    except Exception as e:
        console.print(f"\n[bold red]LM Studio Error:[/bold red] {e}")
        console.print(
            f"[yellow]Tip: Ensure LM Studio is running on {LMSTUDIO_BASE_URL} "
            f"with model '{MODEL_NAME}' loaded.[/yellow]"
        )
        return ""
    console.print("\n")
    return "".join(full_response)


# ─── Save helper ───────────────────────────────────────────────────────────────

def save_spec(content: str, prefix: str, story_id: str = "") -> Path:
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = f"{prefix}_{story_id}_{ts}" if story_id else f"{prefix}_{ts}"
    path = SPECS_DIR / f"{slug}.md"
    path.write_text(content, encoding="utf-8")
    console.print(f"[green]✔ Saved →[/green] [dim]{path}[/dim]\n")
    return path


# ─── LLM auto-suggest helper ───────────────────────────────────────────────────

def suggest_fields(hint: str, fields: dict) -> dict:
    """
    Ask the LLM to suggest values for *fields* (dict of field_name → description/example).
    Uses a fast non-streaming call; returns {} on any failure.
    """
    field_list = "\n".join(f'  "{k}": // {v}' for k, v in fields.items())
    prompt = (
        f"ABP Framework + Angular project context:\n{hint}\n\n"
        f"Return ONLY a valid JSON object (no markdown fences, no extra text) with suggested values "
        f"for these fields:\n{{\n{field_list}\n}}"
    )
    with console.status("[cyan]LLM is suggesting values…[/cyan]", spinner="dots"):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": (
                        "You are a JSON-only code generator for ABP Framework + Angular projects. "
                        "Respond with a single valid JSON object and nothing else — no markdown, "
                        "no explanations, no code fences."
                    )},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=600,
                stream=False,
            )
            raw = resp.choices[0].message.content.strip()
            # Strip accidental markdown fences
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
            return json.loads(raw)
        except Exception as e:
            console.print(f"[yellow]Auto-suggest failed ({e}). Continuing with manual input.[/yellow]")
            return {}


def _smart_prompt(label: str, key: str, suggestions: dict, default: str = "") -> str:
    """
    Prompt the user for a value.  If the LLM produced a suggestion for *key*,
    show it as the default (highlighted) so the user can accept with Enter.
    """
    suggested = suggestions.get(key, "").strip()
    effective_default = suggested or default
    tag = "[dim](LLM ✦)[/dim] " if suggested else ""
    return Prompt.ask(f"[cyan]{label}[/cyan] {tag}", default=effective_default)


def _offer_autofill(command_hint: str) -> dict:
    """
    Ask the user if they want LLM to pre-fill fields.
    Returns a suggestions dict (possibly empty).
    Returns immediately without prompting the LLM if the user says no.
    *command_hint* is shown in the prompt.
    """
    if not Confirm.ask(
        f"[dim]Auto-fill {command_hint} fields with LLM? (one-line description → suggested values)[/dim]",
        default=False,
    ):
        return {}
    hint = Prompt.ask("[cyan]Describe your feature in one line[/cyan]")
    # The actual field keys will be supplied by the caller; we return the hint for them to call suggest_fields
    return {"_hint": hint}


def _read_multiline(prompt_hint: str = "Paste content. Type END on a new line to finish.") -> str:
    console.print(f"[dim]{prompt_hint}[/dim]")
    lines = []
    while True:
        line = input()
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def _load_or_paste_spec(glob_pattern: str = "spec_*.md") -> str:
    saved = sorted(SPECS_DIR.glob(glob_pattern))
    if saved:
        console.print("[dim]Saved specs found:[/dim]")
        for i, f in enumerate(saved, 1):
            console.print(f"  [dim]{i}.[/dim] {f.name}")
        choice = Prompt.ask("Load by number, or Enter to paste manually", default="")
        if choice.isdigit() and 1 <= int(choice) <= len(saved):
            text = saved[int(choice) - 1].read_text(encoding="utf-8")
            console.print(f"[green]Loaded:[/green] {saved[int(choice)-1].name}")
            return text
    return _read_multiline("Paste spec content. Type END to finish.")


# ─── Slash Commands ────────────────────────────────────────────────────────────

def cmd_discovery():
    """/discovery — Analyze raw stakeholder notes → structured problem statement (ABP-aware)."""
    console.print(Panel(
        "[bold]Phase 1 · Discovery Kickoff Analyzer[/bold] — ABP + Angular\n"
        "[dim]Paste stakeholder notes or feature request. Type END on a new line to finish.[/dim]",
        style="cyan"
    ))
    raw = _read_multiline()
    if not raw.strip():
        console.print("[red]No input provided.[/red]")
        return
    p = PROMPTS["discovery"]
    result = stream_llm(p["system"], p["user_template"].format(input=raw), "Discovery Report")
    if result:
        save_spec(result, "discovery")


def cmd_domain():
    """/domain — Design the DDD domain layer for an ABP module (entities, value objects, events)."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]Domain Layer Designer[/bold] — ABP Framework DDD\n"
        "[dim]Design entities, value objects, domain events, and repository interfaces.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("Domain Layer")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "module_name":  "Short module name, e.g. 'Books', 'Orders'",
                "description":  "One-sentence module purpose",
                "multi_tenant": "'Yes' or 'No'",
                "soft_delete":  "'Yes' or 'No'",
                "audit_fields": "e.g. 'FullAudited (created, modified, deleted by/at)'",
            },
        )
    module_name  = _smart_prompt("Module Name",          "module_name",  suggestions, "Books")
    namespace    = _smart_prompt("Root Namespace",        "namespace",    suggestions, ctx["namespace"])
    description  = _smart_prompt("Module Purpose",        "description",  suggestions, "")
    multi_tenant = _smart_prompt("Multi-Tenant?",         "multi_tenant", suggestions, ctx["multi_tenant"])
    soft_delete  = _smart_prompt("Soft Delete Required?", "soft_delete",  suggestions, "Yes")
    audit_fields = _smart_prompt("Audit Fields",          "audit_fields", suggestions,
                                 "FullAudited (created, modified, deleted by/at)")

    p = PROMPTS["domain"]
    user_msg = p["user_template"].format(
        module_name=module_name, namespace=namespace, description=description,
        multi_tenant=multi_tenant, soft_delete=soft_delete, audit_fields=audit_fields
    )
    result = stream_llm(p["system"], user_msg, f"Domain Layer — {module_name}")
    if result:
        save_spec(result, "domain", module_name.lower())


def cmd_appservice():
    """/appservice — Spec for an ABP Application Service with DTOs, validators, and permissions."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]Application Service Spec Generator[/bold] — ABP Framework\n"
        "[dim]Generate complete AppService spec with DTOs, AutoMapper, and permission requirements.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("AppService")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "story_id":         "Story or ticket ID, e.g. 'STORY-001'",
                "module_name":      "Module name, e.g. 'Books'",
                "purpose":          "What the service does in one sentence",
                "crud_ops":         "Comma-separated list of operations needed",
                "permission_prefix":"ABP permission prefix, e.g. 'Acme.BookStore.Books'",
                "business_rules":   "Key business rules, or 'None'",
            },
        )
    story_id          = _smart_prompt("Story ID",          "story_id",         suggestions, "STORY-001")
    module_name       = _smart_prompt("Module Name",        "module_name",      suggestions, "Books")
    namespace         = _smart_prompt("Namespace",          "namespace",        suggestions, f"{ctx['namespace']}.{module_name}")
    purpose           = _smart_prompt("Service Purpose",    "purpose",          suggestions, "")
    crud_ops          = _smart_prompt("CRUD Operations",    "crud_ops",         suggestions, "GetList, Get, Create, Update, Delete")
    permission_prefix = _smart_prompt("Permission Prefix",  "permission_prefix",suggestions, f"{ctx['project_name']}.{module_name}")
    business_rules    = _smart_prompt("Business Rules",     "business_rules",   suggestions, "None specified")

    p = PROMPTS["appservice"]
    user_msg = p["user_template"].format(
        story_id=story_id, module_name=module_name, namespace=namespace,
        purpose=purpose, crud_ops=crud_ops, permission_prefix=permission_prefix,
        business_rules=business_rules
    )
    result = stream_llm(p["system"], user_msg, f"AppService Spec — {story_id}")
    if result:
        save_spec(result, "appservice", story_id)


def cmd_api():
    """/api — Spec the HTTP API layer: routes, verbs, status codes, ABP dynamic proxy."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]HTTP API Layer Spec[/bold] — ABP Framework REST\n"
        "[dim]Define endpoints, authorization, request/response schemas, and Swagger notes.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("HTTP API")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "story_id":     "Story or ticket ID",
                "module_name":  "Module name, e.g. 'Books'",
                "route_prefix": "REST route prefix, e.g. 'book-store/books'",
                "api_version":  "API version, e.g. 'v1'",
                "app_service":  "Interface name, e.g. 'IBookAppService'",
                "auth_required":"'Yes' or 'No'",
            },
        )
    story_id     = _smart_prompt("Story ID",            "story_id",     suggestions, "STORY-001")
    module_name  = _smart_prompt("Module Name",          "module_name",  suggestions, "Books")
    route_prefix = _smart_prompt("Route Prefix",         "route_prefix", suggestions, "book-store/books")
    api_version  = _smart_prompt("API Version",          "api_version",  suggestions, "v1")
    app_service  = _smart_prompt("Application Service",  "app_service",  suggestions, "IBookAppService")
    auth_required= _smart_prompt("Auth Required?",       "auth_required",suggestions, "Yes")

    p = PROMPTS["api"]
    user_msg = p["user_template"].format(
        story_id=story_id, module_name=module_name, route_prefix=route_prefix,
        api_version=api_version, app_service=app_service, auth_required=auth_required
    )
    result = stream_llm(p["system"], user_msg, f"HTTP API Spec — {story_id}")
    if result:
        save_spec(result, "api", story_id)


def cmd_angular():
    """/angular — Spec an Angular feature module: components, services, routing, permissions."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]Angular Module Spec[/bold] — ABP Angular UI\n"
        "[dim]Spec components, routing, ABP proxy services, and permission gates.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("Angular Module")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "story_id":      "Story or ticket ID",
                "module_name":   "Angular feature module name, e.g. 'BooksModule'",
                "route_path":    "Route path segment, e.g. 'books'",
                "proxy_service": "ABP proxy service name, e.g. 'BookService'",
                "permissions":   "Required ABP permission string(s)",
                "ui_components": "List of UI components needed",
                "state_mgmt":    "State management approach",
            },
        )
    story_id     = _smart_prompt("Story ID",               "story_id",      suggestions, "STORY-001")
    module_name  = _smart_prompt("Feature Module Name",     "module_name",   suggestions, "BooksModule")
    route_path   = _smart_prompt("Route Path",              "route_path",    suggestions, "books")
    proxy_service= _smart_prompt("ABP Proxy Service",       "proxy_service", suggestions, "BookService")
    permissions  = _smart_prompt("Required Permissions",    "permissions",   suggestions, f"{ctx['project_name']}.Books.Default")
    ui_components= _smart_prompt("UI Components Needed",    "ui_components", suggestions, "List page, Create/Edit modal, Detail view")
    state_mgmt   = _smart_prompt("State Management",        "state_mgmt",    suggestions, "Component-level RxJS / BehaviorSubject")

    p = PROMPTS["angular"]
    user_msg = p["user_template"].format(
        story_id=story_id, module_name=module_name, route_path=route_path,
        proxy_service=proxy_service, permissions=permissions,
        ui_components=ui_components, state_mgmt=state_mgmt
    )
    result = stream_llm(p["system"], user_msg, f"Angular Module Spec — {story_id}")
    if result:
        save_spec(result, "angular", story_id)


def cmd_spec():
    """/spec — Full-stack ABP + Angular specification (all layers in one document)."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]Full-Stack Spec Generator[/bold] — ABP Framework + Angular\n"
        "[dim]Comprehensive spec covering Domain → AppService → HTTP API → Angular UI.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("Full-Stack Spec")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "story_id":     "Story or ticket ID",
                "module_name":  "Module name",
                "user_story":   "As a <role>, I want <goal> so that <benefit>",
                "current_state":"What exists today, or 'Not yet implemented'",
                "nfr":          "Non-functional requirements (latency, uptime, accessibility)",
                "multi_tenant": "'Yes' or 'No'",
            },
        )
    story_id      = _smart_prompt("Story ID",       "story_id",     suggestions, "STORY-001")
    module_name   = _smart_prompt("Module Name",     "module_name",  suggestions, "Books")
    namespace     = _smart_prompt("Root Namespace",  "namespace",    suggestions, ctx["namespace"])
    user_story    = _smart_prompt("User Story",      "user_story",   suggestions, "")
    current_state = _smart_prompt("Current State",   "current_state",suggestions, "Not yet implemented")
    nfr           = _smart_prompt("NFR Targets",     "nfr",          suggestions, "p95 < 300ms, 99.9% uptime, WCAG AA")
    multi_tenant  = _smart_prompt("Multi-Tenant?",   "multi_tenant", suggestions, ctx["multi_tenant"])
    abp_ver       = _smart_prompt("ABP Version",     "abp_version",  suggestions, ctx["abp_version"])

    p = PROMPTS["spec"]
    user_msg = p["user_template"].format(
        story_id=story_id, module_name=module_name, namespace=namespace,
        user_story=user_story, current_state=current_state, nfr=nfr,
        multi_tenant=multi_tenant, abp_version=abp_ver
    )
    result = stream_llm(p["system"], user_msg, f"Full-Stack Spec — {story_id}")
    if result:
        save_spec(result, "spec", story_id)


def cmd_permissions():
    """/permissions — Design the ABP permission system for a module."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]Permission System Designer[/bold] — ABP Framework\n"
        "[dim]Define PermissionDefinitionProvider entries, role matrix, and Angular gates.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("Permissions")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "module_name": "Module name, e.g. 'Books'",
                "operations":  "Comma-separated list of operations (View, Create, Edit, Delete, Export…)",
            },
        )
    module_name  = _smart_prompt("Module Name",    "module_name",  suggestions, "Books")
    project_name = _smart_prompt("Project Name",   "project_name", suggestions, ctx["project_name"])
    operations   = _smart_prompt("Operations",      "operations",   suggestions, "Default (View), Create, Edit, Delete, Export")
    roles        = Prompt.ask("[cyan]Roles in System[/cyan]", default=ctx["default_roles"])

    p = PROMPTS["permissions"]
    user_msg = p["user_template"].format(
        module_name=module_name, project_name=project_name,
        operations=operations, roles=roles
    )
    result = stream_llm(p["system"], user_msg, f"Permission Spec — {module_name}")
    if result:
        save_spec(result, "permissions", module_name.lower())


def cmd_database():
    """/database — EF Core / database schema spec for an ABP module."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]Database / EF Core Spec[/bold] — ABP Framework\n"
        "[dim]Define tables, indexes, migrations, and seed data.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("Database")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "module_name": "Module name",
                "entities":    "Comma-separated entity names, e.g. 'Book, Author, Category'",
                "table_prefix":"Table prefix, e.g. 'App'",
                "multi_tenant":"'Yes — tenant filter on all tables' or 'No'",
            },
        )
    module_name  = _smart_prompt("Module Name",            "module_name",  suggestions, "Books")
    db_provider  = Prompt.ask("[cyan]DB Provider[/cyan]",                   default=ctx["db_provider"])
    table_prefix = _smart_prompt("Table Prefix",            "table_prefix", suggestions, ctx["table_prefix"])
    entities     = _smart_prompt("Entities to map",         "entities",     suggestions, "Book, Author, Category")
    multi_tenant = _smart_prompt("Multi-Tenant Isolation",  "multi_tenant", suggestions,
                                 "Yes — tenant filter on all tables" if ctx["multi_tenant"] == "Yes" else "No")

    p = PROMPTS["database"]
    user_msg = p["user_template"].format(
        module_name=module_name, db_provider=db_provider, table_prefix=table_prefix,
        entities=entities, multi_tenant=multi_tenant
    )
    result = stream_llm(p["system"], user_msg, f"Database Spec — {module_name}")
    if result:
        save_spec(result, "database", module_name.lower())


def cmd_review():
    """/review — AI quality audit of a spec (ABP + Angular focused)."""
    console.print(Panel(
        "[bold]Spec Quality Reviewer[/bold] — ABP + Angular\n"
        "[dim]Audit spec for ABP-specific gaps, untestable criteria, and Angular coverage.[/dim]",
        style="cyan"
    ))
    spec_text = _load_or_paste_spec("*.md")
    if not spec_text.strip():
        console.print("[red]No spec provided.[/red]")
        return
    p = PROMPTS["review"]
    result = stream_llm(p["system"], p["user_template"].format(spec=spec_text), "Spec Quality Report")
    if result:
        save_spec(result, "review")


def cmd_tests_be():
    """/tests-be — Generate .NET xUnit + NSubstitute + Shouldly test scaffolding."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]Backend Test Generator[/bold] — xUnit + NSubstitute + Shouldly\n"
        "[dim]Paste acceptance criteria (BE), or load from a saved spec. Type END to finish.[/dim]",
        style="cyan"
    ))
    story_id         = Prompt.ask("[cyan]Story ID[/cyan]",         default="STORY-001")
    layer            = Prompt.ask("[cyan]Layer[/cyan]",            default="Application (AppService)")
    namespace        = Prompt.ask("[cyan]Namespace[/cyan]",        default=ctx["namespace"])
    class_under_test = Prompt.ask("[cyan]Class Under Test[/cyan]", default="BookAppService")
    mocks            = Prompt.ask("[cyan]Mocks / Fixtures[/cyan]", default="IBookRepository (NSubstitute)")

    console.print("[dim]Load acceptance criteria from a saved spec, or paste manually.[/dim]")
    criteria = _load_or_paste_spec("appservice_*.md") or _load_or_paste_spec("spec_*.md")
    if not criteria.strip():
        criteria = _read_multiline("Paste acceptance criteria now:")

    if not criteria.strip():
        console.print("[red]No criteria provided.[/red]")
        return
    p = PROMPTS["tests_be"]
    user_msg = p["user_template"].format(
        story_id=story_id, layer=layer, namespace=namespace,
        class_under_test=class_under_test, criteria=criteria, mocks=mocks
    )
    result = stream_llm(p["system"], user_msg, f"Backend Tests — {story_id} / {class_under_test}")
    if result:
        save_spec(result, "tests_be", story_id)


def cmd_tests_fe():
    """/tests-fe — Generate Angular Jest + ATL test scaffolding."""
    console.print(Panel(
        "[bold]Angular Test Generator[/bold] — Jest + Angular Testing Library\n"
        "[dim]Load frontend acceptance criteria from a saved spec, or paste manually.[/dim]",
        style="cyan"
    ))
    story_id       = Prompt.ask("[cyan]Story ID[/cyan]",          default="STORY-001")
    component_name = Prompt.ask("[cyan]Component / Service[/cyan]",default="BookListComponent")
    module_name    = Prompt.ask("[cyan]Feature Module[/cyan]",     default="BooksModule")
    mocks          = Prompt.ask("[cyan]Mock Services[/cyan]",      default="BookService, ToasterService, ConfirmationService")

    console.print("[dim]Load acceptance criteria from a saved spec, or paste manually.[/dim]")
    criteria = _load_or_paste_spec("angular_*.md") or _load_or_paste_spec("spec_*.md")
    if not criteria.strip():
        criteria = _read_multiline("Paste frontend acceptance criteria now:")

    if not criteria.strip():
        console.print("[red]No criteria provided.[/red]")
        return
    p = PROMPTS["tests_fe"]
    user_msg = p["user_template"].format(
        story_id=story_id, component_name=component_name, module_name=module_name,
        criteria=criteria, mocks=mocks
    )
    result = stream_llm(p["system"], user_msg, f"Angular Tests — {story_id} / {component_name}")
    if result:
        save_spec(result, "tests_fe", story_id)


def cmd_gap():
    """/gap — Post-release gap & regression analyzer for living spec updates."""
    console.print(Panel(
        "[bold]Gap & Regression Analyzer[/bold] — ABP + Angular\n"
        "[dim]Feed test results and bug reports to refine your spec.[/dim]",
        style="cyan"
    ))
    spec_text = _load_or_paste_spec("*.md")
    results   = _read_multiline("Paste test results / log:")
    bugs      = _read_multiline("Paste bug report summary (or type END immediately to skip):") or "None"

    p = PROMPTS["gap"]
    user_msg = p["user_template"].format(
        spec=spec_text, results=results, bugs=bugs,
        date=datetime.date.today().isoformat()
    )
    result = stream_llm(p["system"], user_msg, "Gap Analysis & Spec Changelog")
    if result:
        save_spec(result, "gap")


def cmd_fastspec():
    """/fastspec — Lightweight 1-page spec for small ABP + Angular features."""
    console.print(Panel(
        "[bold]Fast-Track Spec[/bold] — Small / Low-Risk ABP + Angular Features\n"
        "[dim]Concise 1-page spec with ABP-aware Definition of Done.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("Fast-Track Spec")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "feature":     "Short feature name",
                "description": "One-sentence description",
                "layers":      "Comma-separated ABP layers affected",
            },
        )
    feature     = _smart_prompt("Feature name",     "feature",     suggestions, "")
    description = _smart_prompt("Brief description", "description", suggestions, "")
    layers      = _smart_prompt("Layers Affected",   "layers",      suggestions, "Domain, Application, Angular UI")

    p = PROMPTS["fastspec"]
    user_msg = p["user_template"].format(feature=feature, description=description, layers=layers)
    result = stream_llm(p["system"], user_msg, f"Fast-Track Spec — {feature}")
    if result:
        save_spec(result, "fastspec", feature.replace(" ", "_").lower())


def cmd_localization():
    """/localization — Spec all ABP localization keys for a feature."""
    ctx = load_project_context()
    console.print(Panel(
        "[bold]Localization Spec[/bold] — ABP JSON Localization\n"
        "[dim]Define all localization keys, reusable ABP keys, and Angular pipe usage.[/dim]",
        style="cyan"
    ))
    af = _offer_autofill("Localization")
    suggestions: dict = {}
    if "_hint" in af:
        suggestions = suggest_fields(
            af["_hint"],
            {
                "module_name": "Module name",
                "feature":     "Feature name within the module",
                "cultures":    "Required cultures, e.g. 'en, tr (Turkish)'",
            },
        )
    module_name = _smart_prompt("Module Name",        "module_name", suggestions, "Books")
    feature     = _smart_prompt("Feature",             "feature",     suggestions, "Book Management")
    cultures    = _smart_prompt("Cultures Required",   "cultures",    suggestions, "en, tr (Turkish)")
    ui_text     = _read_multiline("Paste raw UI text / label list. Type END to finish:")

    p = PROMPTS["localization"]
    user_msg = p["user_template"].format(
        module_name=module_name, feature=feature, cultures=cultures, ui_text=ui_text
    )
    result = stream_llm(p["system"], user_msg, f"Localization Spec — {feature}")
    if result:
        save_spec(result, "localization", module_name.lower())


def cmd_init():
    """/init — Create or update sdd_project.json for this project (LLM-assisted)."""
    console.print(Panel(
        "[bold]Project Initializer[/bold] — SDD CLI\n"
        "[dim]Sets up sdd_project.json so every command uses your project's defaults automatically.[/dim]",
        style="cyan"
    ))
    existing = load_project_context()
    use_llm = Confirm.ask(
        "[dim]Describe your project and let LLM pre-fill the context?[/dim]",
        default=True,
    )
    suggestions: dict = {}
    if use_llm:
        hint = Prompt.ask("[cyan]Describe your project in 1-2 sentences[/cyan]")
        suggestions = suggest_fields(
            hint,
            {
                "project_name":   "Top-level project name, e.g. 'Acme.BookStore'",
                "namespace":      "Root C# namespace",
                "abp_version":    "ABP version, e.g. '8.x'",
                "dotnet_version": ".NET version, e.g. '8.0'",
                "angular_version":"Angular version, e.g. '17+'",
                "db_provider":    "EF Core provider, e.g. 'Entity Framework Core (SQL Server)'",
                "multi_tenant":   "'Yes' or 'No'",
                "default_roles":  "Comma-separated role names",
                "table_prefix":   "Table prefix, e.g. 'App'",
            },
        )
    ctx: dict = {}
    ctx["project_name"]    = _smart_prompt("Project Name",    "project_name",   suggestions, existing["project_name"])
    ctx["namespace"]       = _smart_prompt("Root Namespace",  "namespace",      suggestions, existing["namespace"])
    ctx["abp_version"]     = _smart_prompt("ABP Version",     "abp_version",    suggestions, existing["abp_version"])
    ctx["dotnet_version"]  = _smart_prompt(".NET Version",    "dotnet_version", suggestions, existing["dotnet_version"])
    ctx["angular_version"] = _smart_prompt("Angular Version", "angular_version",suggestions, existing["angular_version"])
    ctx["db_provider"]     = _smart_prompt("DB Provider",     "db_provider",    suggestions, existing["db_provider"])
    ctx["auth"]            = Prompt.ask("[cyan]Auth Provider[/cyan]",             default=existing["auth"])
    ctx["multi_tenant"]    = _smart_prompt("Multi-Tenant?",   "multi_tenant",   suggestions, existing["multi_tenant"])
    ctx["default_roles"]   = _smart_prompt("Default Roles",   "default_roles",  suggestions, existing["default_roles"])
    ctx["table_prefix"]    = _smart_prompt("Table Prefix",    "table_prefix",   suggestions, existing["table_prefix"])
    ctx["description"]     = Prompt.ask("[cyan]Project Description (optional)[/cyan]", default=existing.get("description",""))
    save_project_context(ctx)
    console.print("[green]Project context ready. All commands will use these as defaults.[/green]")


def cmd_context():
    """/context — View or edit the current sdd_project.json."""
    ctx = load_project_context()
    table = Table(title="Project Context (sdd_project.json)", style="cyan", header_style="bold cyan")
    table.add_column("Key",   style="bold white", width=20)
    table.add_column("Value", style="cyan")
    for k, v in ctx.items():
        table.add_row(k, str(v))
    console.print(table)
    if not PROJECT_CONTEXT_FILE.exists():
        console.print("[yellow]No sdd_project.json found — run /init to create one.[/yellow]\n")
        return
    if Confirm.ask("[dim]Edit a value?[/dim]", default=False):
        key = Prompt.ask("[cyan]Key to edit[/cyan]")
        if key in ctx:
            ctx[key] = Prompt.ask(f"[cyan]{key}[/cyan]", default=str(ctx[key]))
            save_project_context(ctx)
        else:
            console.print(f"[red]Unknown key '{key}'[/red]")


def cmd_list():
    """/list — List all saved spec files."""
    files = sorted(SPECS_DIR.glob("*.md"))
    if not files:
        console.print("[yellow]No specs saved yet.[/yellow]")
        return
    table = Table(title="Saved Specifications", style="cyan", header_style="bold cyan")
    table.add_column("#",    style="dim", width=4)
    table.add_column("File", style="white")
    table.add_column("Type", style="green", width=14)
    table.add_column("Size", justify="right", style="dim")
    for i, f in enumerate(files, 1):
        kind = f.stem.split("_")[0].capitalize()
        size = f"{f.stat().st_size // 1024} KB" if f.stat().st_size >= 1024 else f"{f.stat().st_size} B"
        table.add_row(str(i), f.name, kind, size)
    console.print(table)


def cmd_view():
    """/view — Render a saved spec as formatted markdown."""
    cmd_list()
    files = sorted(SPECS_DIR.glob("*.md"))
    if not files:
        return
    choice = Prompt.ask("Enter file number to view")
    if choice.isdigit() and 1 <= int(choice) <= len(files):
        console.print(Markdown(files[int(choice) - 1].read_text(encoding="utf-8")))
    else:
        console.print("[red]Invalid selection.[/red]")


def cmd_config():
    """/config — Show current ABP/Angular stack configuration defaults."""
    ctx = load_project_context()
    # Project context table
    if PROJECT_CONTEXT_FILE.exists():
        ctx_table = Table(title="Project Context  (sdd_project.json)", style="green", header_style="bold green")
        ctx_table.add_column("Key",   style="bold white")
        ctx_table.add_column("Value", style="green")
        for k, v in ctx.items():
            ctx_table.add_row(k.replace("_", " ").title(), str(v))
        console.print(ctx_table)
    else:
        console.print("[yellow]No sdd_project.json — run /init to create one.[/yellow]")
    # Global defaults
    table = Table(title="ABP + Angular Stack Defaults", style="cyan", header_style="bold cyan")
    table.add_column("Setting",  style="bold white")
    table.add_column("Value",    style="cyan")
    for k, v in ABP_DEFAULTS.items():
        table.add_row(k.replace("_", " ").title(), v)
    console.print(table)
    console.print(
        f"\n[dim]LM Studio URL:[/dim] [cyan]{LMSTUDIO_BASE_URL}[/cyan]  "
        f"[dim]Model:[/dim] [cyan]{MODEL_NAME}[/cyan]  "
        f"[dim]Specs dir:[/dim] [cyan]{SPECS_DIR.resolve()}[/cyan]\n"
    )


def cmd_help():
    """/help — Show all available commands."""
    table = Table(title="SDD CLI — ABP Framework + Angular", style="cyan", header_style="bold cyan")
    table.add_column("Command",       style="bold white", width=16)
    table.add_column("Phase",         style="green",      width=6)
    table.add_column("Description")
    rows = [
        # Discovery
        ("/discovery",    "1",  "Stakeholder notes → ABP-aware structured problem statement"),
        # Domain
        ("/domain",       "2a", "Design DDD domain layer: entities, value objects, domain events"),
        ("/database",     "2b", "EF Core schema: tables, indexes, migrations, seed data"),
        ("/permissions",  "2c", "ABP PermissionDefinitionProvider + role matrix + Angular gates"),
        ("/localization", "2d", "ABP JSON localization keys + cultures + Angular pipe notes"),
        # Application
        ("/appservice",   "3",  "AppService spec: DTOs, FluentValidation, AutoMapper, permissions"),
        ("/api",          "4",  "HTTP API spec: routes, verbs, status codes, ABP dynamic proxy"),
        # Frontend
        ("/angular",      "5",  "Angular module spec: components, routing, proxy services, guards"),
        # Full-stack shortcut
        ("/spec",         "2–5","Full-stack spec: all layers in one document"),
        ("/fastspec",     "–",  "Lightweight 1-page spec for small features (< 3 days)"),
        # Quality
        ("/review",       "QA", "AI quality audit — ABP + Angular gap detection"),
        ("/tests-be",     "QA", "Generate xUnit + NSubstitute + Shouldly test scaffolding"),
        ("/tests-fe",     "QA", "Generate Angular Jest + ATL test scaffolding"),
        ("/gap",          "6",  "Post-release gap analyzer — refine living specs"),
        # Utilities
        ("/list",         "–",  "List all saved spec files"),
        ("/view",         "–",  "Render a saved spec as formatted markdown"),
        ("/config",       "–",  "Show ABP/Angular stack defaults"),
        ("/help",         "–",  "Show this help message"),
        ("/exit",         "–",  "Exit the CLI"),
    ]
    for cmd, phase, desc in rows:
        table.add_row(cmd, phase, desc)
    console.print(table)
    console.print(
        f"\n[dim]Model:[/dim] [cyan]{MODEL_NAME}[/cyan]  "
        f"[dim]LM Studio:[/dim] [cyan]{LMSTUDIO_BASE_URL}[/cyan]  "
        f"[dim]Specs saved to:[/dim] [cyan]{SPECS_DIR.resolve()}[/cyan]\n"
    )


# ─── Command Registry ──────────────────────────────────────────────────────────

COMMANDS = {
    "/discovery":    cmd_discovery,
    "/domain":       cmd_domain,
    "/database":     cmd_database,
    "/permissions":  cmd_permissions,
    "/localization": cmd_localization,
    "/appservice":   cmd_appservice,
    "/api":          cmd_api,
    "/angular":      cmd_angular,
    "/spec":         cmd_spec,
    "/fastspec":     cmd_fastspec,
    "/review":       cmd_review,
    "/tests-be":     cmd_tests_be,
    "/tests-fe":     cmd_tests_fe,
    "/gap":          cmd_gap,
    "/list":         cmd_list,
    "/view":         cmd_view,
    "/config":       cmd_config,
    "/help":         cmd_help,
}

# ─── REPL ──────────────────────────────────────────────────────────────────────

def main():
    console.print(Panel.fit(
        "[bold cyan]SDD CLI[/bold cyan]  ·  Spec-Driven Development\n"
        "[bold white]ABP Framework (.NET 8) + Angular[/bold white]\n"
        f"[dim]Model:[/dim] [cyan]{MODEL_NAME}[/cyan]  "
        f"[dim]LM Studio:[/dim] [cyan]{LMSTUDIO_BASE_URL}[/cyan]\n"
        "[dim]Type[/dim] [bold white]/help[/bold white] [dim]to see all commands  ·  "
        "[/dim][bold white]/config[/bold white] [dim]for stack defaults[/dim]",
        border_style="cyan"
    ))
    console.print()

    while True:
        try:
            raw = Prompt.ask("[bold cyan]sdd[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye![/dim]")
            break

        if not raw:
            continue

        cmd = raw.split()[0].lower()

        if cmd in ("/exit", "/quit", "/q"):
            console.print("[dim]Bye![/dim]")
            break
        elif cmd in COMMANDS:
            try:
                COMMANDS[cmd]()
            except KeyboardInterrupt:
                console.print("\n[yellow]Interrupted.[/yellow]")
        else:
            console.print(
                f"[red]Unknown command:[/red] [bold]{cmd}[/bold]  "
                "[dim]— type /help for available commands[/dim]"
            )


if __name__ == "__main__":
    main()