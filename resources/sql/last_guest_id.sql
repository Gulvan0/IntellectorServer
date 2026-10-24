SELECT
    MAX(CAST(SUBSTR(authorized_as, 2) AS UNSIGNED))
FROM (
    SELECT
        authorized_as
    FROM
        restrequestlog
    UNION ALL
    SELECT
        authorized_as
    FROM
        wslog
) AS src
WHERE
    authorized_as LIKE "\_%"
