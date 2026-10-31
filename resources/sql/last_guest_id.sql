SELECT
    MAX(CAST(SUBSTR(player_ref, 2) AS UNSIGNED))
FROM (
    SELECT
        white_player_ref AS player_ref
    FROM
        game
    UNION ALL
    SELECT
        black_player_ref AS player_ref
    FROM
        game
) AS src
WHERE
    player_ref LIKE "\_%"
