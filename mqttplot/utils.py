from .app import ensure_topic_db, get_meta_db


def refresh_topic_stats_for_top_level(top_level: str) -> None:
    """
    Recompute topic_stats entries for all topics stored in <config.DATA_DB_DIR>/<top_level>.db
    using v2 compact schema:
      - topics(id, topic)
      - messages(topic_id, ts, value)   # ts is epoch seconds

    Updates the main metadata DB so the UI counts reflect retention purges.

    Canonical columns written:
      - topic, top_level, message_count, first_seen, last_seen, min_val, max_val
    """
    db_path = os.path.join(config.DATA_DB_DIR, f"{top_level}.db")
    if not os.path.exists(db_path):
        return

    data_db = sqlite3.connect(db_path)
    data_db.row_factory = sqlite3.Row
    ensure_topic_db(data_db)
    cur = data_db.cursor()

    # Aggregate remaining data by full topic via join on topics
    cur.execute("""
        SELECT
            t.topic AS topic,
            COUNT(*) AS message_count,
            MIN(m.ts) AS first_seen,
            MAX(m.ts) AS last_seen,
            MIN(m.value) AS min_val,
            MAX(m.value) AS max_val
        FROM messages m
        JOIN topics t ON t.id = m.topic_id
        GROUP BY t.topic
        ORDER BY t.topic
    """)
    rows = cur.fetchall()
    data_db.close()

    main = get_meta_db()

    # Remove existing stats for this top-level (topics have NO leading slash in your system)
    prefix = f"{top_level}/%"
    exact = f"{top_level}"
    main.execute("DELETE FROM topic_stats WHERE topic LIKE ? OR topic = ?", (prefix, exact))

    # Insert refreshed stats (canonical)
    for r in rows:
        topic = r["topic"]
        main.execute("""
            INSERT INTO topic_stats(topic, top_level, message_count, first_seen, last_seen, min_val, max_val)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET
                top_level=excluded.top_level,
                message_count=excluded.message_count,
                first_seen=excluded.first_seen,
                last_seen=excluded.last_seen,
                min_val=excluded.min_val,
                max_val=excluded.max_val
        """, (
            topic,
            top_level,
            int(r["message_count"]),
            float(r["first_seen"]) if r["first_seen"] is not None else None,
            float(r["last_seen"]) if r["last_seen"] is not None else None,
            float(r["min_val"]) if r["min_val"] is not None else None,
            float(r["max_val"]) if r["max_val"] is not None else None,
        ))

        # Ensure topic_meta exists for the topic (public defaults to 1)
        main.execute("""
            INSERT INTO topic_meta(topic, public)
            VALUES (?, 1)
            ON CONFLICT(topic) DO NOTHING
        """, (topic,))

    main.commit()
