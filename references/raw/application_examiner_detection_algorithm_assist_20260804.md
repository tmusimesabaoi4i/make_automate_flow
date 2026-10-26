# Expected Application Number and Primary Examiner Detection Algorithm

## Abstract Input Patterns

```text
PATTERN 1:
    "特許庁 [FamilyName] 様"

PATTERN 2:
    "特許庁 [DepartmentName] [FamilyName] 様"

PATTERN 3:
    "特許庁 [DepartmentName] [FamilyName] 審査官"

PATTERN 4:
    "特許庁 [DepartmentName] [FamilyName] 審査官殿"

PATTERN 5:
    "特許庁 [DepartmentName] 審査官 [FullName] 様"

PATTERN 6:
    "[FamilyName] 審査官"

PATTERN 7:
    "[FamilyName] 審査官殿"

PATTERN 8:
    "[FamilyName] 審査官様"

PATTERN 9:
    "[FullName] 審査官"

PATTERN 10:
    "特許庁の[FamilyName]です"

PATTERN 11:
    "特許庁[DepartmentName] [FullName]"

PATTERN 12:
    "[FamilyNameInHiragana] 審査官殿"
```

## Detection and Completion Algorithm

```text
ALGORITHM DetectExpectedApplicationNumberAndPrimaryExaminer

INPUT:
    RawEmailBody
    OptionalEmailSubject
    OptionalExaminerDirectory

OUTPUT:
    ExpectedApplicationNumber
    ExpectedPrimaryExaminerName

BEGIN

    normalizedBody = NormalizeEmailText(RawEmailBody)
    normalizedSubject = NormalizeEmailText(OptionalEmailSubject)

    emailSections = SplitEmailThread(normalizedBody)

    applicationCandidates = EMPTY ARRAY
    examinerCandidates = EMPTY ARRAY

    FOR EACH section IN emailSections

        threadDepth = section.ThreadDepth
        sectionText = section.Text

        applicationCandidatesInSection =
            ExtractApplicationNumberCandidates(sectionText)

        FOR EACH candidate IN applicationCandidatesInSection

            candidate.ThreadDepth = threadDepth
            candidate.Score =
                CalculateApplicationNumberScore(candidate)

            ADD candidate TO applicationCandidates

        END FOR

        examinerCandidatesInSection =
            ExtractExaminerCandidates(sectionText)

        FOR EACH candidate IN examinerCandidatesInSection

            candidate.ThreadDepth = threadDepth
            candidate.Context =
                GetSurroundingText(
                    sectionText,
                    candidate.MatchPosition,
                    80
                )

            candidate.Score =
                CalculateExaminerCandidateScore(candidate)

            IF candidate is found in the current message THEN
                candidate.Score = candidate.Score + 100
            ELSE
                candidate.Score =
                    candidate.Score - (threadDepth * 20)
            END IF

            IF candidate is found near the beginning
               of the email section
            THEN
                candidate.Score = candidate.Score + 40
            END IF

            IF candidate is explicitly followed
               or preceded by "審査官"
            THEN
                candidate.Score = candidate.Score + 80
            END IF

            IF candidate is preceded by
               "特許庁" or a JPO department name
            THEN
                candidate.Score = candidate.Score + 40
            END IF

            IF candidate is followed by
               "様", "殿", or "先生"
            THEN
                candidate.Score = candidate.Score + 10
            END IF

            IF candidate is found in an external party signature,
               participant list, Cc line, applicant description,
               inventor description, or attorney description
            THEN
                candidate.Score = candidate.Score - 100
            END IF

            ADD candidate TO examinerCandidates

        END FOR

    END FOR

    subjectApplicationCandidates =
        ExtractApplicationNumberCandidates(normalizedSubject)

    FOR EACH candidate IN subjectApplicationCandidates

        candidate.ThreadDepth = 0
        candidate.Score = candidate.Score + 180

        ADD candidate TO applicationCandidates

    END FOR

    applicationCandidates =
        NormalizeAndMergeApplicationCandidates(
            applicationCandidates
        )

    examinerCandidates =
        NormalizeAndMergeExaminerCandidates(
            examinerCandidates
        )

    FOR EACH examinerCandidate IN examinerCandidates

        IF examinerCandidate contains a full name THEN

            examinerCandidate.NameType = "FullName"

        ELSE IF examinerCandidate contains
                a family name only
        THEN

            examinerCandidate.NameType = "FamilyNameOnly"

        ELSE IF examinerCandidate contains
                a hiragana name only
        THEN

            examinerCandidate.NameType = "HiraganaName"

        END IF

    END FOR

    fullNameCandidates =
        FILTER examinerCandidates
        WHERE NameType = "FullName"

    incompleteNameCandidates =
        FILTER examinerCandidates
        WHERE NameType = "FamilyNameOnly"
           OR NameType = "HiraganaName"

    FOR EACH incompleteCandidate IN incompleteNameCandidates

        threadMatches =
            FindMatchingFullNamesInSameThread(
                incompleteCandidate,
                fullNameCandidates
            )

        IF exactly one thread match exists THEN

            incompleteCandidate.Name =
                threadMatches[0].Name

            incompleteCandidate.NameWasCompleted = TRUE
            incompleteCandidate.Score =
                incompleteCandidate.Score + 30

        ELSE IF more than one thread match exists THEN

            incompleteCandidate.NameWasCompleted = FALSE

        ELSE IF OptionalExaminerDirectory IS NOT EMPTY THEN

            directoryMatches =
                FindMatchingNamesInDirectory(
                    incompleteCandidate.Name,
                    OptionalExaminerDirectory
                )

            IF exactly one directory match exists THEN

                incompleteCandidate.Name =
                    directoryMatches[0].FullName

                incompleteCandidate.NameWasCompleted = TRUE
                incompleteCandidate.Score =
                    incompleteCandidate.Score + 10

            ELSE

                incompleteCandidate.NameWasCompleted = FALSE

            END IF

        END IF

    END FOR

    bestApplication =
        SelectHighestScoringApplicationNumber(
            applicationCandidates
        )

    FOR EACH examinerCandidate IN examinerCandidates

        IF bestApplication IS NOT NULL
           AND examinerCandidate appears in the same
               email section as bestApplication
        THEN
            examinerCandidate.Score =
                examinerCandidate.Score + 30
        END IF

        IF bestApplication IS NOT NULL
           AND examinerCandidate appears repeatedly
               in sections concerning bestApplication
        THEN
            examinerCandidate.Score =
                examinerCandidate.Score + 20
        END IF

    END FOR

    bestExaminer =
        SelectHighestScoringPrimaryExaminer(
            examinerCandidates
        )

    RETURN:
        ExpectedApplicationNumber =
            IF bestApplication IS NULL
            THEN NULL
            ELSE bestApplication.Number

        ExpectedPrimaryExaminerName =
            IF bestExaminer IS NULL
            THEN NULL
            ELSE bestExaminer.Name

END
```

## Examiner Candidate Extraction

```text
FUNCTION ExtractExaminerCandidates(text)

    result = EMPTY ARRAY

    patterns = [
        "審査官補 [Name]",
        "審査官 [Name]",
        "[Name] 審査官",
        "[Name] 審査官様",
        "[Name] 審査官殿",
        "[JpoDepartment] [Name] 様",
        "[JpoDepartment] [Name] 殿",
        "特許庁の[Name]です",
        "特許庁の[Name]でございます",
        "[JpoDepartment]の[Name]です",
        "[JpoDepartment] [FullName]"
    ]

    FOR EACH pattern IN patterns

        matches = FindAllMatches(text, pattern)

        FOR EACH match IN matches

            name = CleanCandidateName(match.Name)

            IF name IS NOT EMPTY
               AND name is not an organization name
               AND name is not an external party name
            THEN

                ADD {
                    Name: name,
                    MatchedText: match.Text,
                    MatchPosition: match.Position,
                    PatternType: pattern
                } TO result

            END IF

        END FOR

    END FOR

    RETURN result

END FUNCTION
```

## Family Name and Hiragana Name Completion

```text
FUNCTION FindMatchingFullNamesInSameThread(
    incompleteCandidate,
    fullNameCandidates
)

    result = EMPTY ARRAY

    FOR EACH fullNameCandidate IN fullNameCandidates

        IF incompleteCandidate is a family name only
           AND fullNameCandidate.Name starts with
               incompleteCandidate.Name
        THEN
            ADD fullNameCandidate TO result
        END IF

        IF incompleteCandidate is written in hiragana
           AND ReadingOf(fullNameCandidate.Name) starts with
               incompleteCandidate.Name
        THEN
            ADD fullNameCandidate TO result
        END IF

    END FOR

    RETURN distinct full names from result

END FUNCTION
```

## Primary Examiner Selection

```text
FUNCTION SelectHighestScoringPrimaryExaminer(candidates)

    validCandidates =
        FILTER candidates
        WHERE candidate is not an external party
          AND candidate is not an applicant
          AND candidate is not an inventor
          AND candidate is not an attorney
          AND candidate is not merely an attendee
          AND candidate is not merely a Cc recipient

    rankedCandidates =
        SORT validCandidates BY Score DESCENDING

    IF rankedCandidates IS EMPTY THEN
        RETURN NULL
    END IF

    bestCandidate = rankedCandidates[0]

    IF bestCandidate.NameType = "FullName" THEN
        RETURN bestCandidate
    END IF

    IF bestCandidate.NameType = "FamilyNameOnly"
       AND bestCandidate.NameWasCompleted = TRUE
    THEN
        RETURN bestCandidate
    END IF

    IF bestCandidate.NameType = "HiraganaName"
       AND bestCandidate.NameWasCompleted = TRUE
    THEN
        RETURN bestCandidate
    END IF

    RETURN bestCandidate without forcing
        an unverified full-name conversion

END FUNCTION
```

## Decision Rules

```text
1. Prefer an examiner name in the current message addressee.

2. Accept a family name only when no verified full name is available.

3. Search quoted messages for a self-introduction or JPO signature
   that contains the corresponding full name.

4. Complete a family name only when exactly one matching full name
   exists in the same email thread.

5. Complete a hiragana name only when exactly one matching reading
   exists in the same email thread or examiner directory.

6. Do not guess a full name when multiple examiners share the same
   family name or reading.

7. Prefer explicit examiner expressions such as:
       "審査官 [Name]"
       "[Name] 審査官"
       "[Name] 審査官殿"

8. When the role word is omitted, accept:
       "特許庁 [Name] 様"
   only if the name appears in the email addressee area.

9. Use the subject, current message, quoted self-introductions,
   and JPO signatures as mutually supporting evidence.

10. Return exactly one primary examiner:
        the valid candidate with the highest score.

11. Return the family name or hiragana name as-is when full-name
    completion cannot be verified.

12. Select the application number that appears in the subject or
    current message and is most strongly associated with the
    selected primary examiner.
```
