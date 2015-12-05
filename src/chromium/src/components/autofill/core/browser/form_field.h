// Copyright 2013 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_AUTOFILL_CORE_BROWSER_FORM_FIELD_H_
#define COMPONENTS_AUTOFILL_CORE_BROWSER_FORM_FIELD_H_

#include <vector>

#include "base/basictypes.h"
#include "base/gtest_prod_util.h"
#include "base/memory/scoped_ptr.h"
#include "base/strings/string16.h"
#include "components/autofill/core/browser/field_types.h"

namespace autofill {

class AutofillField;
class AutofillScanner;

// Represents a logical form field in a web form.  Classes that implement this
// interface can identify themselves as a particular type of form field, e.g.
// name, phone number, or address field.
class FormField {
 public:
  virtual ~FormField() {}

  // Classifies each field in |fields| with its heuristically detected type.
  // The association is stored into |map|.  Each field has a derived unique name
  // that is used as the key into the |map|.
  static void ParseFormFields(const std::vector<AutofillField*>& fields,
                              bool is_form_tag,
                              ServerFieldTypeMap* map);

 protected:
  // A bit-field used for matching specific parts of a field in question.
  enum MatchType {
    // Attributes.
    MATCH_LABEL      = 1 << 0,
    MATCH_NAME       = 1 << 1,

    // Input types.
    MATCH_TEXT       = 1 << 2,
    MATCH_EMAIL      = 1 << 3,
    MATCH_TELEPHONE  = 1 << 4,
    MATCH_SELECT     = 1 << 5,
    MATCH_TEXT_AREA  = 1 << 6,
    MATCH_PASSWORD   = 1 << 7,
    MATCH_NUMBER     = 1 << 8,
    MATCH_ALL_INPUTS =
        MATCH_TEXT | MATCH_EMAIL | MATCH_TELEPHONE | MATCH_SELECT |
        MATCH_TEXT_AREA | MATCH_PASSWORD | MATCH_NUMBER,

    // By default match label and name for input/text types.
    MATCH_DEFAULT    = MATCH_LABEL | MATCH_NAME | MATCH_TEXT,
  };

  // When parsing a field's label and name separately with a given pattern:
  enum ParseNameLabelResult {
    RESULT_MATCH_NONE,       // No match with the label or name.
    RESULT_MATCH_LABEL,      // Only the label matches the pattern.
    RESULT_MATCH_NAME,       // Only the name matches the pattern.
    RESULT_MATCH_NAME_LABEL  // Name and label both match the pattern.
  };

  // Only derived classes may instantiate.
  FormField() {}

  // Attempts to parse a form field with the given pattern.  Returns true on
  // success and fills |match| with a pointer to the field.
  static bool ParseField(AutofillScanner* scanner,
                         const base::string16& pattern,
                         AutofillField** match);

  // Parses the stream of fields in |scanner| with regular expression |pattern|
  // as specified in the |match_type| bit field (see |MatchType|).  If |match|
  // is non-NULL and the pattern matches, the matched field is returned.
  // A |true| result is returned in the case of a successful match, false
  // otherwise.
  static bool ParseFieldSpecifics(AutofillScanner* scanner,
                                  const base::string16& pattern,
                                  int match_type,
                                  AutofillField** match);

  // Like ParseFieldSpecifics(), but applies |pattern| against the name and
  // label of the current field separately. If the return value is
  // RESULT_MATCH_NAME_LABEL, then |scanner| advances and |match| is filled if
  // it is non-NULL. Otherwise |scanner| does not advance and |match| does not
  // change.
  static ParseNameLabelResult ParseNameAndLabelSeparately(
      AutofillScanner* scanner,
      const base::string16& pattern,
      int match_type,
      AutofillField** match);

  // Attempts to parse a field with an empty label.  Returns true
  // on success and fills |match| with a pointer to the field.
  static bool ParseEmptyLabel(AutofillScanner* scanner, AutofillField** match);

  // Adds an association between a field and a type to |map|.
  static bool AddClassification(const AutofillField* field,
                                ServerFieldType type,
                                ServerFieldTypeMap* map);

  // Returns true iff |type| matches |match_type|.
  static bool MatchesFormControlType(const std::string& type, int match_type);

  // Derived classes must implement this interface to supply field type
  // information.  |ParseFormFields| coordinates the parsing and extraction
  // of types from an input vector of |AutofillField| objects and delegates
  // the type extraction via this method.
  virtual bool ClassifyField(ServerFieldTypeMap* map) const = 0;

 private:
  FRIEND_TEST_ALL_PREFIXES(FormFieldTest, Match);

  // Function pointer type for the parsing function that should be passed to the
  // ParseFormFieldsPass() helper function.
  typedef scoped_ptr<FormField> ParseFunction(AutofillScanner* scanner);

  // Matches |pattern| to the contents of the field at the head of the
  // |scanner|.
  // Returns |true| if a match is found according to |match_type|, and |false|
  // otherwise.
  static bool MatchAndAdvance(AutofillScanner* scanner,
                              const base::string16& pattern,
                              int match_type,
                              AutofillField** match);

  // Matches the regular expression |pattern| against the components of |field|
  // as specified in the |match_type| bit field (see |MatchType|).
  static bool Match(const AutofillField* field,
                    const base::string16& pattern,
                    int match_type);

  // Perform a "pass" over the |fields| where each pass uses the supplied
  // |parse| method to match content to a given field type.
  // |fields| is both an input and an output parameter.  Upon exit |fields|
  // holds any remaining unclassified fields for further processing.
  // Classification results of the processed fields are stored in |map|.
  static void ParseFormFieldsPass(ParseFunction parse,
                                  std::vector<AutofillField*>* fields,
                                  ServerFieldTypeMap* map);

  DISALLOW_COPY_AND_ASSIGN(FormField);
};

}  // namespace autofill

#endif  // COMPONENTS_AUTOFILL_CORE_BROWSER_FORM_FIELD_H_