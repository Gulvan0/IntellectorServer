SELECT
    MAX(CAST(SUBSTR(authorized_as, 2) AS UNSIGNED))
FROM (
    SELECT
        authorized_as
    FROM
        test_schema.restrequestlog
    UNION ALL
    SELECT
        authorized_as
    FROM
        test_schema.wslog
) AS src
WHERE
    authorized_as LIKE "\_%"
