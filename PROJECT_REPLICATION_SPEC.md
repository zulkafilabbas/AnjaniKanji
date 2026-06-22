# Anjani Kanji: Product and Rebuild Specification

This document describes the app at a level intended for someone rebuilding it as a web application from scratch. It focuses on behavior, architecture, data flow, and feature completeness rather than the original implementation details.

## 1. Purpose

Anjani Kanji is a kanji study and review application built around spaced repetition, manual practice, and visual recognition.

Its main goals are:

1. Let a learner import kanji lists from CSV files and turn them into study decks.
2. Track kanji across one or more study profiles.
3. Schedule reviews using a spaced-repetition system with daily queues.
4. Support fast study sessions with flashcard-style interaction.
5. Show study history, queue counts, and per-day activity in a calendar.
6. Provide backup/export and restore/import for whole profiles.
7. Animate stroke order for kanji when stroke data is available.

In plain terms, this is a kanji memorization and practice tool that combines:

- deck import
- dashboard-based queue selection
- flashcards
- review scheduling
- session history
- profile backup/restore
- typography customization

## 2. Product Shape

The app is organized like a study workspace with a left navigation sidebar and a main content area.

The major user-facing sections are:

- Dashboard
- Library
- Calendar
- Learn
- Settings

The interface is responsive. On narrow screens it collapses into a more compact rail/sidebar behavior, while on wide screens it expands into a full sidebar and larger study surface.

## 3. Core Concepts

### 3.1 Profiles

A profile represents a learner identity and study configuration. Profiles let the app keep separate scheduling state for the same kanji decks.

Each profile stores:

- profile name
- active deck
- daily new-card limit
- scheduler mode
- desired retention target
- typography preferences

The app creates a default profile automatically on first run.

### 3.2 Decks

A deck is created from one imported CSV file.

The deck stores:

- deck id
- deck name
- original filename
- import timestamp
- total card count
- ordered list of characters in the deck

Each deck is effectively a kanji list that can be selected as the active study source for a profile.

### 3.3 Kanji Records

Kanji are global records shared across decks.

Each kanji record stores:

- the character itself
- one or more meanings
- source filenames where it appeared
- deck ids that contain it
- first-created timestamp
- last-seen timestamp

This means if the same character appears in multiple imported CSVs, the app merges metadata instead of duplicating the character record.

### 3.4 Cards

Cards are the per-profile, per-deck study state for each character.

A card stores:

- study state: `new`, `review`, or `relearning`
- stability
- difficulty
- retrievability
- next due timestamp
- elapsed days
- scheduled days
- repetition count
- lapse count
- last review timestamp
- relearn-until timestamp

Cards are what the scheduler updates after each rating.

### 3.5 Sessions

A session is a record of a study run.

It stores:

- session id
- profile id
- deck id
- start and end timestamps
- session mode
- sample size
- ordered kanji list
- seen list

The app uses sessions both as a study state container and as history for the calendar view.

### 3.6 Review Logs

Every rating action creates a review log entry.

This gives the app an audit trail for:

- which card was reviewed
- what rating was given
- when it was reviewed
- previous due date
- next due date
- scheduler state at the moment of review

### 3.7 Sources

Every imported CSV file is tracked as a source record with:

- filename
- import timestamp
- row count
- linked deck id

This powers the import history section.

## 4. Data Storage Architecture

The app uses local persistent storage.

### 4.1 Storage Layer

The storage layer owns:

- SQLite schema creation and migration
- data access
- card creation and updates
- import/export persistence
- session persistence
- review log persistence
- stroke SVG caching

### 4.2 Persistence Model

The main database tables are:

- `profiles`
- `decks`
- `kanji`
- `cards`
- `sessions`
- `sources`
- `review_logs`
- `stroke_cache`

### 4.3 Storage Behavior

The database is designed to be durable and local-first:

- data is written to a per-user app data directory
- SQLite runs in WAL mode
- the storage layer uses locking for thread safety
- cards are created automatically for each profile when a deck is present
- deleting a deck or profile also removes dependent records

### 4.4 Default Data Initialization

On first run, the app ensures a default profile exists.

If decks already exist, the default profile points to the most recently imported deck.

## 5. Study Scheduling

The app supports two scheduler modes.

### 5.1 Built-in FSRS Mode

The default scheduler is a pure-Python FSRS implementation.

It calculates:

- updated stability
- updated difficulty
- retrievability
- next due date
- relearning transitions

The built-in scheduler is light enough to run without the research package.

### 5.2 Package-Backed DR Mode

There is a second scheduler mode that delegates interval calculation to a local copy of the `SSP-MMC-FSRS` package.

This mode is optional and depends on the extra package being available in the same environment.

### 5.3 Rating Inputs

The study UI supports four ratings:

- again
- hard
- good
- easy

These are mapped into the scheduler logic.

### 5.4 Scheduling Rules

The scheduler behaves like this:

- new cards start with an initial stability/difficulty estimate on first rating
- success ratings move the card into `review`
- failure ratings move the card into `relearning`
- relearning uses a short same-day delay
- review cards get a computed interval in days
- the active profile’s desired retention influences interval length

### 5.5 Daily Queue Construction

The dashboard queue is assembled from three sets:

- relearning cards due now
- review cards due now
- new cards up to the profile’s daily cap

The ordering is designed to prioritize urgent cards first, then due reviews, then new cards.

## 6. Import Model

### 6.1 CSV Format

Import files are CSVs where:

- column 1 is the kanji character
- columns 2 through N are meanings

Examples in the repository show rows like:

- `日,sun,day`
- `月,moon,month`
- `火,fire`

The parser is permissive and supports quoted fields.

### 6.2 Import Semantics

When a CSV is imported:

1. The file becomes a new deck.
2. A source record is created.
3. Unique kanji are added to the global kanji table.
4. Existing kanji are merged rather than duplicated.
5. Each profile gets new cards for the imported characters.
6. The deck is available for selection immediately.

### 6.3 Merge Behavior

If a kanji already exists:

- meanings are unioned
- sources are unioned
- deck membership is unioned

This means the app treats the kanji table as a shared vocabulary index.

## 7. Backup and Restore

The app can export and import whole profiles.

### 7.1 Export

Export produces a JSON payload containing:

- profile
- decks
- sources
- kanji
- cards
- sessions
- review logs

The exported file name is based on the profile name.

### 7.2 Import Restore

A backup can be restored in two ways:

- overwrite/restore into the original profile identity
- import as a copy, creating a new profile with a new id and adjusted display name

### 7.3 Restore Rules

When importing a profile payload:

- decks, kanji, sessions, cards, and logs are restored
- shared kanji metadata is merged with existing records
- duplicate-profile mode rewrites ids so the imported profile becomes independent

## 8. Screens and User Experience

## 8.1 Dashboard

The dashboard is the main control surface.

It shows:

- current profile and deck
- queue counts for re-learn, review, and new cards
- studied-today count
- next scheduled review time
- manual selection grid
- action controls for starting study sessions

### Dashboard actions

The dashboard supports:

- starting the full daily queue
- starting a session from selected kanji only
- starting a queue filtered to re-learn, review, or new cards
- choosing the session duration

### Dashboard manual selection

The manual grid lets the learner click kanji tiles to add or remove them from a custom practice session.

Tile visuals change based on:

- whether a kanji is selected
- whether it has been practiced
- whether it is in review or relearning state
- how many times it has been practiced

## 8.2 Library

The library page is a deck management and import center.

It shows:

- all available decks
- the active deck
- import instructions
- the import log
- imported source history

This screen is also where the user can trigger CSV import and see how many rows were added or merged.

## 8.3 Calendar

The calendar page visualizes study activity by day.

It shows:

- a month header with previous/next controls
- weekday labels
- a grid of days
- study intensity based on the number of seen kanji
- tooltips with the date and sampled studied characters

This is not a scheduling calendar. It is a study-history calendar.

## 8.4 Learn

The learn view is the focused flashcard session.

It shows:

- a top bar with the app name, nav, deck name, and current position
- an action bar with session shortcuts
- a horizontal filmstrip of session cards
- a central flashcard
- rating buttons
- a footer with current character details

### Learn card behavior

The card can display in several modes:

- kanji front
- stroke animation
- flipped meaning side
- empty state when nothing is available

### Learn controls

Supported actions include:

- previous card
- next card
- flip card
- play stroke animation
- rate card with again/hard/good/easy
- select current character from session
- end session
- reset session

### Keyboard shortcuts

The app supports keyboard-driven study:

- left arrow: previous
- right arrow: next
- space: play stroke animation
- `f`: flip
- `s`: select current kanji
- `1`: again
- `2`: hard
- `3`: good
- `4`: easy

## 8.5 Settings

Settings are where profile-level configuration lives.

The page supports:

- switching profiles
- creating a profile
- deleting a profile
- editing typography preferences
- changing scheduler mode
- changing desired retention
- choosing daily new-card cap
- importing a backup
- importing a backup as a copy
- exporting a backup

Typography controls include:

- Japanese text size
- flipped Japanese text size
- meaning text size
- Japanese font family
- meaning font family

## 9. Flashcard Interaction Model

The card interaction is intentionally simple:

- click the card or press play to animate strokes
- flip to reveal meanings
- rate once you know the answer
- move through the queue with arrows

The UI is structured to minimize friction during review.

The flashcard footer surfaces the most relevant context:

- current character
- last seen time
- due status
- session position
- deck total

## 10. Stroke Animation

One distinguishing feature is animated stroke order playback.

### 10.1 Data Source

Stroke diagrams are pulled from KanjiVG SVG files.

### 10.2 Caching

Downloaded SVGs are cached locally so the app does not fetch the same character repeatedly.

### 10.3 Rendering

The app:

- parses SVG path data
- samples curves into polylines
- converts them into canvas shapes
- progressively reveals stroke segments over time

### 10.4 Fallback Behavior

If stroke data is missing or unavailable:

- the app shows a friendly message
- the card still works as a normal flashcard

## 11. Responsive Layout

The app adapts to screen width.

### Wide layout

On larger screens:

- the sidebar expands
- the dashboard has more room
- the study card can be wider
- the filmstrip shows more tiles at once

### Compact layout

On smaller screens:

- the sidebar collapses into a rail
- study surfaces are more compact
- the filmstrip shows fewer visible tiles
- some panels are hidden or reduced to maintain usability

The important point is that it is not just a static desktop layout. It intentionally changes behavior based on viewport size.

## 12. UI Architecture

The app is organized as a layered client-side application.

### 12.1 App Shell

The top-level app object owns:

- the current view
- selected profile
- selected deck
- current session
- selection state
- preview state
- animation state
- sidebar state
- month state
- import/export state

### 12.2 Controllers

The controller layer coordinates:

- creating profiles
- importing decks
- building queue sessions
- rating cards
- loading dashboard state
- exporting and importing backups
- generating calendar study data

### 12.3 Storage

The storage layer is responsible for persistence and business-state mutation.

### 12.4 View Models

The UI does not consume raw database rows directly. Instead it uses typed view models for:

- kanji tiles
- flashcard state
- dashboard summary metrics
- status log entries

This keeps the UI rendering logic mostly declarative.

### 12.5 Components

The main reusable components are:

- sidebar
- dashboard header
- kanji card
- calendar view
- import view

## 13. State Transitions

### 13.1 Starting a Session

When the user starts a queue or manual session:

1. The app builds a `Session` object from the current queues or selection.
2. The session is saved.
3. The UI switches into learn mode.
4. The session snapshot is captured so it can be reset later.
5. The first card is loaded.
6. The active character is marked as seen.

### 13.2 Moving Through Cards

As the user advances:

- the position updates
- the current card is marked seen if needed
- stroke data for the active kanji is loaded
- the filmstrip updates to highlight the current card

### 13.3 Rating a Card

When a rating is submitted:

1. The card is persisted with new scheduling values.
2. A review log entry is created.
3. The kanji’s last-seen timestamp is updated.
4. The app refreshes dashboard data.
5. The next card is shown, or the session ends if the queue is complete.

### 13.4 Resetting a Session

Reset restores the original pre-session state:

- card states are rolled back
- last-seen timestamps are restored
- review logs created after the session started are removed
- the session restarts from the beginning

## 14. Navigation Model

The navigation model is simple and direct.

The primary views are:

- dashboard
- library
- calendar
- learn
- settings

The sidebar and the top navigation both point to the same view state.

## 15. Themes and Visual Design

The visual style uses a dark palette with green accents.

The layout relies on:

- bordered panels
- compact metric cards
- strong contrast text
- subtle elevation
- consistent radii and spacing

The design is calm and study-oriented rather than flashy.

## 16. Functional Requirements for a Web Rebuild

If rebuilding this as a web app, the minimum feature set should include:

1. Local or server-backed persistence for profiles, decks, cards, sessions, and logs.
2. CSV import that creates decks and merges kanji metadata.
3. A dashboard with queue counts and manual selection.
4. A flashcard study mode with flip, rating, navigation, and stroke playback.
5. FSRS-like scheduling with daily queue generation.
6. Calendar history grouped by study day.
7. Profile backup export/import.
8. Typography customization.
9. Responsive behavior for narrow and wide layouts.
10. Optional advanced scheduler mode if the matching runtime exists.

## 17. Non-Goals and Caveats

This app is practical, but it is not a polished commercial product.

Important caveats:

- the built-in FSRS implementation is intentionally lightweight
- the optional package-backed scheduler depends on local environment support
- the repository includes a separate reference package for one scheduler mode
- the app is optimized for personal study workflows

## 18. Suggested Web-App Mapping

If someone wanted to rebuild this as a web app, a good high-level mapping would be:

- frontend SPA for navigation, sessions, cards, and calendar
- persistence layer using either local storage, IndexedDB, or a backend database
- serverless or backend API for import/export if multi-device sync is desired
- SVG or canvas-based stroke playback for kanji drawing animation
- session state managed in a dedicated study controller or store

The important thing is to preserve the behavior, not the exact Python/Flet implementation.

## 19. Summary

Anjani Kanji is a kanji flashcard and scheduler app built around:

- CSV-based deck import
- per-profile spaced repetition
- manual and queue-driven study sessions
- stroke-order animation
- study history visualization
- profile backup and restore
- responsive UI with a compact study workflow

The app’s architecture is clean enough to recreate in another stack as long as the new implementation preserves the same data model and state transitions.
