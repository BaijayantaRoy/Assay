from sqlmodel import Session, select
from backend.database import engine, create_db_and_tables
from backend.models import Organization, Project, Prompt, PromptVersion
from backend.seed_library import seed_library
from backend.seed_models import seed_models

# --- Starter Prompt Templates ---
STARTER_PROMPTS = [
    {
        "name": "Customer Support Reply",
        "description": "Generate professional customer support responses",
        "tags": ["support", "email", "starter"],
        "content": """You are a helpful and professional customer support agent for {{company_name}}.

A customer has reached out with the following message:
---
{{customer_message}}
---

Please write a friendly, empathetic, and solution-oriented reply. Keep the tone {{tone}} and the response concise (under 200 words).

Key guidelines:
- Acknowledge their concern
- Provide a clear solution or next step
- End with an offer to help further""",
        "commit_message": "Initial template — customer support reply",
    },
    {
        "name": "Code Review Assistant",
        "description": "Analyze code and provide constructive feedback",
        "tags": ["coding", "review", "starter"],
        "content": """You are an expert {{language}} code reviewer.

Review the following code and provide feedback:

```{{language}}
{{code}}
```

Provide your review in this format:

## Summary
A brief overview of what the code does.

## Issues Found
List any bugs, security issues, or logic errors.

## Suggestions
Recommend improvements for readability, performance, and best practices.

## Rating
Rate the code quality from 1-10 with a brief justification.""",
        "commit_message": "Initial template — code review",
    },
    {
        "name": "Content Summarizer",
        "description": "Summarize long-form content into key points",
        "tags": ["writing", "summarization", "starter"],
        "content": """Summarize the following {{content_type}} into {{format}}:

---
{{content}}
---

Requirements:
- Maximum {{max_points}} key points
- Use clear, concise language
- Preserve the most important information
- Maintain the original tone and intent""",
        "commit_message": "Initial template — content summarizer",
    },
    {
        "name": "SQL Query Generator",
        "description": "Generate SQL queries from natural language descriptions",
        "tags": ["coding", "sql", "starter"],
        "content": """You are a {{database_type}} SQL expert.

Given the following database schema:
{{schema}}

Write a SQL query to: {{request}}

Requirements:
- Use proper SQL syntax for {{database_type}}
- Include comments explaining complex parts
- Optimize for performance where possible
- Return only the SQL query, no explanations""",
        "commit_message": "Initial template — SQL query generator",
    },
    {
        "name": "Meeting Notes to Action Items",
        "description": "Extract action items from meeting transcripts",
        "tags": ["productivity", "meetings", "starter"],
        "content": """Extract action items from the following meeting notes:

---
{{meeting_notes}}
---

Format each action item as:
- [ ] **[Owner]**: Task description (Due: date if mentioned)

Also provide:
1. **Key Decisions Made**: List any decisions reached
2. **Open Questions**: List unresolved items
3. **Next Meeting Topics**: Suggested agenda items for follow-up""",
        "commit_message": "Initial template — meeting action items",
    },
]


def seed():
    create_db_and_tables()
    with Session(engine) as session:
        # Check if org exists
        org = session.exec(
            select(Organization).where(Organization.slug == "default-org")
        ).first()
        if not org:
            print("Creating default organization...")
            org = Organization(name="My Organization", slug="default-org")
            session.add(org)
            session.commit()
            session.refresh(org)

        # Check if project exists
        project = session.exec(
            select(Project).where(Project.name == "My First Project")
        ).first()
        if not project:
            print("Creating default project...")
            project = Project(
                name="My First Project",
                description="A starter project with template prompts",
                organization_id=org.id,
            )
            session.add(project)
            session.commit()
            session.refresh(project)

        # Seed starter prompts (only if project has no prompts)
        existing_prompts = session.exec(
            select(Prompt).where(Prompt.project_id == project.id)
        ).all()

        if len(existing_prompts) == 0:
            print("Seeding starter prompt templates...")
            import re

            for tmpl in STARTER_PROMPTS:
                prompt = Prompt(
                    name=tmpl["name"],
                    description=tmpl["description"],
                    project_id=project.id,
                    tags=tmpl["tags"],
                )
                session.add(prompt)
                session.commit()
                session.refresh(prompt)

                # Extract variables
                variables = list(
                    set(re.findall(r"\{\{\s*(\w+)\s*\}\}", tmpl["content"]))
                )

                version = PromptVersion(
                    prompt_id=prompt.id,
                    version_number=1,
                    content=tmpl["content"],
                    config={"model": "gpt-6.1-sol"},
                    variables=variables,
                    commit_message=tmpl["commit_message"],
                )
                session.add(version)
                session.commit()
                session.refresh(version)

                prompt.latest_version_id = version.id
                session.add(prompt)
                session.commit()
            print(f"  -> Created {len(STARTER_PROMPTS)} starter prompts")

    print("Database seeded successfully!")
    
    # Also seed library and models
    seed_library()
    seed_models()


if __name__ == "__main__":
    seed()
