# Graduation progress input

Use an object with:

- `profile`: `campus`, `college`, `major`, `admission_year`, and optional `tracks`.
- `sources`: official source objects with `id`, `url`, `checked_on`, and optional `title`.
- `courses`: course objects with `course_code`, `title`, `credits`, `status`
  (`completed`, `in_progress`, `failed`, or `withdrawn`), and zero or more
  `categories`.
- `facts`: non-course facts such as language certification or chapel passes.
- `requirements`: explicit rules with a unique `id`, `label`, `type`, and
  `source_id`.
- `official_progress`: existing Underwood rows with `program` (first, second,
  or third major; minor; micro major; track or depth), `requirement`, `earned`,
  `in_progress`, `recognized`, `substituted`, `cross_recognized`, and
  `missing`.

Supported requirement types:

- `total_credits`: minimum unique completed credits across all courses.
- `category_credits`: minimum completed credits whose `categories` include
  `category`.
- `course_set`: require `minimum_count` distinct courses from `course_codes`.
- `fact`: require `facts[key]` to equal `expected`.

Set `allow_overlap: false` on a category requirement when the supplied official
rule says its credits cannot overlap with earlier non-overlap category
requirements. The calculator reports incomplete source linkage and unknown
course categorization instead of guessing.

Do not create `official_progress` by pressing the official self-diagnosis
button unless the student explicitly requested that action. Underwood warns
that special department requirements may be incomplete, so this snapshot and
the local calculation remain advisory.
