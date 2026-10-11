"""Initial schema (spec v1.1 §4).

Revision ID: 0001_init
Revises:
Create Date: 2026-10-11
"""

from __future__ import annotations

from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

EMBED_DIM = 384


def _has_timescale() -> bool:
    bind = op.get_bind()
    row = bind.exec_driver_sql(
        "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'"
    ).first()
    return row is not None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    timescale = _has_timescale()
    if timescale:
        op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # ---------------------------------------------------------------- sources
    op.execute(
        """
        CREATE TABLE sources (
          id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          name                 TEXT UNIQUE NOT NULL,
          display_name         TEXT NOT NULL,
          domain               TEXT NOT NULL,
          type                 TEXT NOT NULL CHECK (type IN ('api','crawl','manual','feed')),
          method               TEXT,
          country              TEXT,
          currency             TEXT,
          base_url             TEXT NOT NULL,
          rate_limit_rps       NUMERIC NOT NULL DEFAULT 0.5 CHECK (rate_limit_rps >= 0),
          robots_url           TEXT,
          robots_checked_at    TIMESTAMPTZ,
          robots_hash          TEXT,
          legal_review_status  TEXT NOT NULL DEFAULT 'pending'
                               CHECK (legal_review_status IN ('approved','pending','blocked')),
          legal_reviewed_by    TEXT,
          legal_reviewed_at    TIMESTAMPTZ,
          tos_url              TEXT,
          api_key_ref          TEXT,
          crawl_status         TEXT NOT NULL DEFAULT 'ok'
                               CHECK (crawl_status IN ('ok','review_required','failing','disabled')),
          crawl_status_reason  TEXT,
          crawl_status_at      TIMESTAMPTZ,
          extractor            TEXT NOT NULL DEFAULT 'generic',
          js_required          BOOLEAN NOT NULL DEFAULT false,
          cache_ttl_hours      INT NOT NULL DEFAULT 48,
          trust_score          NUMERIC NOT NULL DEFAULT 0.5 CHECK (trust_score BETWEEN 0 AND 1),
          affiliate_template   TEXT,
          warehouse_country    TEXT,
          warehouse_city       TEXT,
          warehouse_lat        DOUBLE PRECISION,
          warehouse_lon        DOUBLE PRECISION,
          ships_to             TEXT[] NOT NULL DEFAULT '{}',
          active               BOOLEAN NOT NULL DEFAULT true,
          created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX sources_domain_idx ON sources (domain)")

    # ----------------------------------------------------------------- images
    op.execute(
        """
        CREATE TABLE images (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          source_id    UUID REFERENCES sources(id) ON DELETE SET NULL,
          source_url   TEXT NOT NULL UNIQUE,
          s3_key       TEXT,
          width        INT,
          height       INT,
          phash        TEXT,
          attribution  TEXT NOT NULL,
          license      TEXT NOT NULL DEFAULT 'source-hosted'
                       CHECK (license IN ('source-hosted','manufacturer','cc-by','cc-by-sa','cc0','submitted')),
          created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          -- Rule: only redistributable licenses may be copied to object storage.
          CHECK (s3_key IS NULL OR license <> 'source-hosted')
        )
        """
    )
    op.execute("CREATE INDEX images_phash_idx ON images (phash)")

    # ------------------------------------------------------------- components
    op.execute(
        f"""
        CREATE TABLE components (
          id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          slug              TEXT UNIQUE NOT NULL,
          mpn               TEXT NOT NULL,
          mpn_norm          TEXT NOT NULL,
          manufacturer      TEXT,
          manufacturer_norm TEXT NOT NULL DEFAULT '',
          gtin              TEXT,
          category          TEXT NOT NULL,
          subcategory       TEXT,
          title             TEXT NOT NULL,
          short_desc        TEXT,
          long_desc         TEXT,
          prose_md          TEXT,
          prose_reviewed    BOOLEAN NOT NULL DEFAULT false,
          specs             JSONB NOT NULL DEFAULT '{{}}',
          specs_norm        JSONB NOT NULL DEFAULT '{{}}',
          package           TEXT,
          lifecycle         TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (lifecycle IN ('active','nrnd','obsolete','unknown')),
          primary_image     UUID REFERENCES images(id) ON DELETE SET NULL,
          datasheet_url     TEXT,
          datasheet_host    TEXT,
          embedding         vector({EMBED_DIM}),
          popularity        DOUBLE PRECISION NOT NULL DEFAULT 0,
          status            TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active','merged','retired')),
          merged_into       UUID REFERENCES components(id),
          created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX components_embedding_hnsw ON components "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE UNIQUE INDEX components_mpn_mfr_uq ON components (mpn_norm, manufacturer_norm) "
        "WHERE status = 'active'"
    )
    op.execute("CREATE INDEX components_gtin_idx ON components (gtin) WHERE gtin IS NOT NULL")
    op.execute("CREATE INDEX components_category_idx ON components (category, subcategory)")
    op.execute("CREATE INDEX components_mfr_idx ON components (manufacturer_norm)")

    op.execute(
        """
        CREATE TABLE component_images (
          component_id  UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
          image_id      UUID NOT NULL REFERENCES images(id) ON DELETE CASCADE,
          position      INT NOT NULL DEFAULT 0,
          PRIMARY KEY (component_id, image_id)
        )
        """
    )

    # ------------------------------------------------------------ crawl_pages
    op.execute(
        """
        CREATE TABLE crawl_pages (
          id             BIGSERIAL PRIMARY KEY,
          url            TEXT NOT NULL,
          url_hash       TEXT UNIQUE NOT NULL,
          final_url      TEXT,
          source_id      UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          fetched_at     TIMESTAMPTZ NOT NULL,
          http_status    INT,
          content_hash   TEXT,
          content_type   TEXT,
          etag           TEXT,
          last_modified  TEXT,
          raw_ref        TEXT,
          error          TEXT,
          extracted_at   TIMESTAMPTZ,
          expires_at     TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX crawl_pages_source_fetched ON crawl_pages (source_id, fetched_at DESC)")
    op.execute("CREATE INDEX crawl_pages_expires ON crawl_pages (expires_at) WHERE raw_ref IS NOT NULL")

    # --------------------------------------------------------------- listings
    op.execute(
        f"""
        CREATE TABLE listings (
          id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          source_id             UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          url                   TEXT NOT NULL,
          url_hash              TEXT UNIQUE NOT NULL,
          source_sku            TEXT,
          gtin                  TEXT,
          raw_title             TEXT NOT NULL,
          raw_mpn               TEXT,
          mpn_trusted           BOOLEAN NOT NULL DEFAULT false,  -- MPN from a structured field/API, not a title guess
          raw_manufacturer      TEXT,
          package               TEXT,
          specs                 JSONB NOT NULL DEFAULT '{{}}',
          image_url             TEXT,
          datasheet_url         TEXT,
          snippet               TEXT CHECK (snippet IS NULL OR length(snippet) <= 300),
          embedding             vector({EMBED_DIM}),
          component_id          UUID REFERENCES components(id) ON DELETE SET NULL,
          match_confidence      NUMERIC CHECK (match_confidence IS NULL OR match_confidence BETWEEN 0 AND 1),
          match_method          TEXT CHECK (match_method IS NULL OR match_method IN
                                  ('gtin','mpn_exact','mpn_mfr_fuzzy','mpn_fuzzy','embedding','manual','new')),
          condition             TEXT NOT NULL DEFAULT 'new'
                                CHECK (condition IN ('new','used','refurb','unknown')),
          in_stock              BOOLEAN,
          stock_qty             INT,
          ships_from            TEXT,
          ships_to              TEXT[] NOT NULL DEFAULT '{{}}',
          extraction_method     TEXT,
          consecutive_failures  INT NOT NULL DEFAULT 0,
          first_seen            TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_seen             TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_attempt          TIMESTAMPTZ,
          active                BOOLEAN NOT NULL DEFAULT true
        )
        """
    )
    op.execute("CREATE INDEX listings_component_idx ON listings (component_id) WHERE active")
    op.execute("CREATE INDEX listings_source_idx ON listings (source_id)")
    op.execute("CREATE INDEX listings_unresolved_idx ON listings (first_seen) WHERE component_id IS NULL")

    # ------------------------------------------------------------------ prices
    op.execute(
        """
        CREATE TABLE price_snapshots (
          time             TIMESTAMPTZ NOT NULL,
          listing_id       UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
          currency         TEXT NOT NULL,
          price_minor      BIGINT NOT NULL CHECK (price_minor >= 0),
          price_breaks     JSONB NOT NULL DEFAULT '[]',
          moq              INT NOT NULL DEFAULT 1,
          shipping_minor   BIGINT,
          tax_included     BOOLEAN,
          observed_at      TIMESTAMPTZ NOT NULL
        )
        """
    )
    if timescale:
        op.execute("SELECT create_hypertable('price_snapshots', 'time')")
    op.execute("CREATE INDEX price_snapshots_listing_time ON price_snapshots (listing_id, time DESC)")
    op.execute("CREATE INDEX price_snapshots_time ON price_snapshots (time)")

    op.execute(
        """
        CREATE TABLE price_current (
          listing_id        UUID PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
          currency          TEXT NOT NULL,
          price_minor       BIGINT NOT NULL,
          price_breaks      JSONB NOT NULL DEFAULT '[]',
          moq               INT NOT NULL DEFAULT 1,
          shipping_minor    BIGINT,
          price_usd_minor   BIGINT NOT NULL,
          landed_usd_minor  BIGINT NOT NULL,
          observed_at       TIMESTAMPTZ NOT NULL,
          updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE price_daily (
          day          DATE NOT NULL,
          listing_id   UUID NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
          currency     TEXT NOT NULL,
          min_minor    BIGINT NOT NULL,
          max_minor    BIGINT NOT NULL,
          close_minor  BIGINT NOT NULL,
          usd_min_minor BIGINT NOT NULL,
          PRIMARY KEY (listing_id, day)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE fx_rates (
          day       DATE NOT NULL,
          currency  TEXT NOT NULL,
          per_usd   NUMERIC(20, 8) NOT NULL CHECK (per_usd > 0),
          source    TEXT NOT NULL,
          PRIMARY KEY (day, currency)
        )
        """
    )

    # -------------------------------------------------------------- use cases
    op.execute(
        """
        CREATE TABLE use_cases (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          component_id    UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
          slug            TEXT NOT NULL,
          title           TEXT NOT NULL,
          difficulty      TEXT CHECK (difficulty IS NULL OR difficulty IN ('beginner','intermediate','advanced')),
          summary         TEXT NOT NULL CHECK (length(summary) <= 600),
          steps           JSONB NOT NULL DEFAULT '[]',
          wiring_diagram  UUID REFERENCES images(id) ON DELETE SET NULL,
          thumbnail_url   TEXT,
          code_language   TEXT,
          code_snippet    TEXT,
          code_license    TEXT,
          source_type     TEXT NOT NULL CHECK (source_type IN ('reddit','youtube','blog','forum','github','editorial')),
          source_url      TEXT NOT NULL,
          source_author   TEXT,
          source_license  TEXT,
          verified_by     UUID[] NOT NULL DEFAULT '{}',
          upvotes         INT NOT NULL DEFAULT 0,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (component_id, source_url),
          UNIQUE (component_id, slug),
          -- Code is only stored when its license permits redistribution.
          CHECK (code_snippet IS NULL OR code_license IS NOT NULL)
        )
        """
    )

    # ------------------------------------------------------------- datasheets
    op.execute(
        """
        CREATE TABLE datasheets (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          component_id  UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
          url           TEXT NOT NULL,
          host          TEXT NOT NULL,
          revision      TEXT,
          page_count    INT,
          language      TEXT,
          is_primary    BOOLEAN NOT NULL DEFAULT false,
          checked_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (component_id, url)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX datasheets_one_primary ON datasheets (component_id) WHERE is_primary"
    )

    # --------------------------------------------------------------- shipping
    op.execute(
        """
        CREATE TABLE ship_estimates (
          id            BIGSERIAL PRIMARY KEY,
          source_id     UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          from_country  TEXT NOT NULL,
          to_country    TEXT NOT NULL,
          to_city       TEXT NOT NULL DEFAULT '',
          cost_minor    BIGINT NOT NULL,
          currency      TEXT NOT NULL,
          eta_days_min  INT NOT NULL,
          eta_days_max  INT NOT NULL CHECK (eta_days_max >= eta_days_min),
          method        TEXT NOT NULL DEFAULT 'standard',
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (source_id, to_country, to_city, method)
        )
        """
    )

    # ---------------------------------------------------- analytics & traffic
    op.execute(
        """
        CREATE TABLE queries (
          time             TIMESTAMPTZ NOT NULL,
          query_norm       TEXT NOT NULL,
          result_count     INT,
          clicked_listing  UUID,
          user_country     TEXT,
          session_hash     TEXT
        )
        """
    )
    if timescale:
        op.execute("SELECT create_hypertable('queries', 'time')")
    op.execute("CREATE INDEX queries_time_idx ON queries (time)")
    op.execute("CREATE INDEX queries_norm_idx ON queries (query_norm, time DESC)")

    op.execute(
        """
        CREATE TABLE component_views_daily (
          day           DATE NOT NULL,
          component_id  UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
          views         INT NOT NULL DEFAULT 0,
          PRIMARY KEY (component_id, day)
        )
        """
    )

    # --------------------------------------------------------- users / alerts
    op.execute(
        """
        CREATE TABLE users (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          email       CITEXT UNIQUE NOT NULL,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE price_alerts (
          id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          component_id   UUID NOT NULL REFERENCES components(id) ON DELETE CASCADE,
          target_minor   BIGINT NOT NULL CHECK (target_minor > 0),
          currency       TEXT NOT NULL,
          quantity       INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
          ship_to        TEXT NOT NULL,
          active         BOOLEAN NOT NULL DEFAULT true,
          armed          BOOLEAN NOT NULL DEFAULT true,
          last_fired_at  TIMESTAMPTZ,
          created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX price_alerts_component_idx ON price_alerts (component_id) WHERE active")

    # ------------------------------------------------- audit / review / legal
    op.execute(
        """
        CREATE TABLE merge_audit (
          id              BIGSERIAL PRIMARY KEY,
          at              TIMESTAMPTZ NOT NULL DEFAULT now(),
          action          TEXT NOT NULL CHECK (action IN ('attach','detach','create','merge','split')),
          listing_id      UUID,
          from_component  UUID,
          to_component    UUID,
          confidence      NUMERIC,
          method          TEXT,
          actor           TEXT NOT NULL,
          details         JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX merge_audit_listing_idx ON merge_audit (listing_id)")
    op.execute("CREATE INDEX merge_audit_component_idx ON merge_audit (to_component)")

    op.execute(
        """
        CREATE TABLE review_queue (
          id           BIGSERIAL PRIMARY KEY,
          kind         TEXT NOT NULL CHECK (kind IN ('match','llm_extraction','source','guide','prose','submission','takedown')),
          ref_id       TEXT NOT NULL,
          reason       TEXT NOT NULL,
          payload      JSONB NOT NULL DEFAULT '{}',
          status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','rejected')),
          created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          resolved_at  TIMESTAMPTZ,
          resolved_by  TEXT
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX review_queue_open_uq ON review_queue (kind, ref_id) WHERE status = 'open'"
    )

    op.execute(
        """
        CREATE TABLE llm_extraction_log (
          id               BIGSERIAL PRIMARY KEY,
          created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          url              TEXT NOT NULL,
          model            TEXT NOT NULL,
          input_hash       TEXT NOT NULL,
          output           JSONB,
          confidence       NUMERIC,
          cost_usd_micros  BIGINT NOT NULL DEFAULT 0,
          committed        BOOLEAN NOT NULL DEFAULT false,
          error            TEXT
        )
        """
    )

    op.execute(
        """
        CREATE TABLE takedown_requests (
          id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          domain         TEXT NOT NULL,
          contact_email  CITEXT NOT NULL,
          reason         TEXT NOT NULL,
          status         TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','accepted','rejected')),
          created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          resolved_at    TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE TABLE data_reports (
          id            BIGSERIAL PRIMARY KEY,
          component_id  UUID REFERENCES components(id) ON DELETE CASCADE,
          listing_id    UUID REFERENCES listings(id) ON DELETE CASCADE,
          field         TEXT NOT NULL,
          message       TEXT NOT NULL CHECK (length(message) <= 2000),
          status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','fixed','rejected')),
          created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE guides (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          slug          TEXT UNIQUE NOT NULL,
          title         TEXT NOT NULL,
          body_md       TEXT NOT NULL,
          query_cluster TEXT,
          status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','rejected')),
          reviewed_by   TEXT,
          reviewed_at   TIMESTAMPTZ,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          -- Rule (§10.4): nothing auto-generated is published without a human reviewer.
          CHECK (status <> 'published' OR reviewed_by IS NOT NULL)
        )
        """
    )

    # ---------------------------------------------------------- crawl priority
    op.execute(
        """
        CREATE VIEW crawl_priority AS
        WITH v AS (
          SELECT component_id, sum(views) AS views
          FROM component_views_daily
          WHERE day > current_date - 7
          GROUP BY component_id
        ), r AS (
          SELECT component_id, percent_rank() OVER (ORDER BY views) AS pr FROM v
        )
        SELECT
          l.id          AS listing_id,
          l.source_id,
          l.url,
          l.last_seen,
          l.last_attempt,
          l.consecutive_failures,
          CASE
            WHEN r.pr >= 0.95 THEN interval '6 hours'
            WHEN r.pr >= 0.50 THEN interval '24 hours'
            ELSE interval '7 days'
          END AS recrawl_every,
          COALESCE(l.last_attempt, l.last_seen)
            + (CASE
                 WHEN r.pr >= 0.95 THEN interval '6 hours'
                 WHEN r.pr >= 0.50 THEN interval '24 hours'
                 ELSE interval '7 days'
               END) * power(2, LEAST(l.consecutive_failures, 4)) AS next_due
        FROM listings l
        JOIN sources s ON s.id = l.source_id
        LEFT JOIN r ON r.component_id = l.component_id
        WHERE l.active
          AND s.active
          AND s.legal_review_status = 'approved'
          AND s.crawl_status = 'ok'
          AND s.type = 'crawl'
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS crawl_priority")
    for table in (
        "guides",
        "data_reports",
        "takedown_requests",
        "llm_extraction_log",
        "review_queue",
        "merge_audit",
        "price_alerts",
        "users",
        "component_views_daily",
        "queries",
        "ship_estimates",
        "datasheets",
        "use_cases",
        "fx_rates",
        "price_daily",
        "price_current",
        "price_snapshots",
        "listings",
        "crawl_pages",
        "component_images",
        "components",
        "images",
        "sources",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
