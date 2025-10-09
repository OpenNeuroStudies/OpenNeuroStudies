# Generate OpenNeuroStudies Release Entry

Generate a new release entry for the CHANGES file following CPAN::Changes::Spec format.

## Steps

1. **Determine new version number**:
   - Read current CHANGES file to find latest version
   - Use format: `0.YYYYMMDD.PATCH` (e.g., `0.20251009.0`)
   - If releasing on same day as previous release, increment PATCH (e.g., `0.20251009.1`)

2. **Analyze git history since last release**:
   - Find git tag matching latest CHANGES version (e.g., `0.20251009.0`)
   - Run: `git log <last_tag>..HEAD --oneline --no-merges`
   - Count commits by category (feat:, fix:, docs:, refactor:, etc.)

3. **Check study metadata changes** (if studies.tsv exists):
   - Compare studies.tsv between current HEAD and last release tag
   - Count: new studies added, studies updated, studies removed
   - Example: `git diff <last_tag>..HEAD -- studies.tsv | grep -c "^+study-"`

4. **Generate concise release summary**:
   - Focus on high-level changes, not individual commits
   - Prioritize study collection statistics over implementation details
   - Format as CPAN Changelog with 2-space indentation
   - Example structure:
     ```
     0.YYYYMMDD.PATCH YYYY-MM-DD
       - Added 150 new study datasets
       - Updated metadata for 23 studies
       - Infrastructure: <concise summary of major changes>
       - Documentation: <concise summary if significant>
     ```

5. **Prepend to CHANGES file**:
   - Insert new entry at the top of CHANGES file
   - Preserve existing entries below
   - Maintain blank line between entries

6. **Create git tag**:
   - Tag current HEAD with version: `git tag <version>`
   - Annotated tag with message: `git tag -a <version> -m "Release <version>"`

7. **Verification**:
   - Show the new CHANGES entry
   - Confirm git tag was created: `git tag -l | grep <version>`
   - Remind user to push tag: `git push origin <version>`

## Output Format

Provide:
1. The new CHANGES entry text
2. Git commands executed
3. Summary statistics (commits analyzed, studies changed, etc.)
4. Next steps for user (commit CHANGES, push tag)

## Important Notes

- Be concise - prioritize study collection growth over implementation minutiae
- Use present tense for change descriptions (e.g., "Add" not "Added")
- Group related changes together
- Omit routine maintenance commits unless significant
- ALWAYS create matching git tag
