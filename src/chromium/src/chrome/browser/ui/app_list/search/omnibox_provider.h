// Copyright 2013 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_UI_APP_LIST_SEARCH_OMNIBOX_PROVIDER_H_
#define CHROME_BROWSER_UI_APP_LIST_SEARCH_OMNIBOX_PROVIDER_H_

#include "base/basictypes.h"
#include "base/memory/scoped_ptr.h"
#include "components/omnibox/autocomplete_controller_delegate.h"
#include "ui/app_list/search_provider.h"

class AppListControllerDelegate;
class AutocompleteController;
class AutocompleteResult;
class Profile;

namespace app_list {

// OmniboxProvider wraps AutocompleteController to provide omnibox results.
class OmniboxProvider : public SearchProvider,
                        public AutocompleteControllerDelegate {
 public:
  explicit OmniboxProvider(Profile* profile,
                           AppListControllerDelegate* list_controller);
  ~OmniboxProvider() override;

  // SearchProvider overrides:
  void Start(bool is_voice_query, const base::string16& query) override;
  void Stop() override;

 private:
  // Populates result list from AutocompleteResult.
  void PopulateFromACResult(const AutocompleteResult& result);

  // AutocompleteControllerDelegate overrides:
  void OnResultChanged(bool default_match_changed) override;

  Profile* profile_;
  AppListControllerDelegate* list_controller_;

  // The omnibox AutocompleteController that collects/sorts/dup-
  // eliminates the results as they come in.
  scoped_ptr<AutocompleteController> controller_;

  // Whether the current query is a voice query.
  bool is_voice_query_;

  DISALLOW_COPY_AND_ASSIGN(OmniboxProvider);
};

}  // namespace app_list

#endif  // CHROME_BROWSER_UI_APP_LIST_SEARCH_OMNIBOX_PROVIDER_H_
