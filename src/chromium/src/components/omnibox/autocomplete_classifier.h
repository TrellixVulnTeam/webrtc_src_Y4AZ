// Copyright (c) 2012 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef COMPONENTS_OMNIBOX_AUTOCOMPLETE_CLASSIFIER_H_
#define COMPONENTS_OMNIBOX_AUTOCOMPLETE_CLASSIFIER_H_

#include "base/basictypes.h"
#include "base/compiler_specific.h"
#include "base/memory/scoped_ptr.h"
#include "base/strings/string16.h"
#include "components/keyed_service/core/keyed_service.h"
#include "components/metrics/proto/omnibox_event.pb.h"
#include "components/omnibox/autocomplete_scheme_classifier.h"

class AutocompleteController;
struct AutocompleteMatch;
class GURL;

class AutocompleteClassifier : public KeyedService {
 public:
  // Bitmap of AutocompleteProvider::Type values describing the default set of
  // providers queried for the omnibox.  Intended to be passed to
  // AutocompleteController().
  static const int kDefaultOmniboxProviders;

  AutocompleteClassifier(
      scoped_ptr<AutocompleteController> controller_,
      scoped_ptr<AutocompleteSchemeClassifier> scheme_classifier);
  ~AutocompleteClassifier() override;

  // Given some string |text| that the user wants to use for navigation,
  // determines how it should be interpreted.
  // |prefer_keyword| should be true the when keyword UI is onscreen; see
  // comments on AutocompleteController::Start().
  // |allow_exact_keyword_match| should be true when treating the string as a
  // potential keyword search is valid; see
  // AutocompleteInput::allow_exact_keyword_match().
  // |page_classification| gives information about the context (e.g., is the
  // user on a search results page doing search term replacement); this may
  // be useful in deciding how the input should be interpreted.
  // |match| should be a non-NULL outparam that will be set to the default
  // match for this input, if any (for invalid input, there will be no default
  // match, and |match| will be left unchanged).  |alternate_nav_url| is a
  // possibly-NULL outparam that, if non-NULL, will be set to the navigational
  // URL (if any) in case of an accidental search; see comments on
  // AutocompleteResult::alternate_nav_url_ in autocomplete.h.
  void Classify(const base::string16& text,
                bool prefer_keyword,
                bool allow_exact_keyword_match,
                metrics::OmniboxEventProto::PageClassification
                    page_classification,
                AutocompleteMatch* match,
                GURL* alternate_nav_url);

 private:
  // KeyedService:
  void Shutdown() override;

  scoped_ptr<AutocompleteController> controller_;
  scoped_ptr<AutocompleteSchemeClassifier> scheme_classifier_;

  // Are we currently in Classify? Used to verify Classify isn't invoked
  // recursively, since this can corrupt state and cause crashes.
  bool inside_classify_;

  DISALLOW_IMPLICIT_CONSTRUCTORS(AutocompleteClassifier);
};

#endif  // COMPONENTS_OMNIBOX_AUTOCOMPLETE_CLASSIFIER_H_
