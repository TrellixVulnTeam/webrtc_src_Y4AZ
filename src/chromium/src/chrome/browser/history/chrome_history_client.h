// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef CHROME_BROWSER_HISTORY_CHROME_HISTORY_CLIENT_H_
#define CHROME_BROWSER_HISTORY_CHROME_HISTORY_CLIENT_H_

#include <set>

#include "base/callback_forward.h"
#include "base/callback_list.h"
#include "base/macros.h"
#include "base/memory/scoped_ptr.h"
#include "components/bookmarks/browser/base_bookmark_model_observer.h"
#include "components/history/core/browser/history_client.h"

class GURL;

namespace bookmarks {
class BookmarkModel;
class BookmarkNode;
}

// This class implements history::HistoryClient to abstract operations that
// depend on Chrome environment.
class ChromeHistoryClient : public history::HistoryClient,
                            public bookmarks::BaseBookmarkModelObserver {
 public:
  explicit ChromeHistoryClient(bookmarks::BookmarkModel* bookmark_model);
  ~ChromeHistoryClient() override;

  // history::HistoryClient implementation.
  void OnHistoryServiceCreated(
      history::HistoryService* history_service) override;
  void Shutdown() override;
  bool CanAddURL(const GURL& url) override;
  void NotifyProfileError(sql::InitStatus init_status) override;
  scoped_ptr<history::HistoryBackendClient> CreateBackendClient() override;

 private:
  // bookmarks::BaseBookmarkModelObserver implementation.
  void BookmarkModelChanged() override;

  // bookmarks::BookmarkModelObserver implementation.
  void BookmarkNodeRemoved(bookmarks::BookmarkModel* bookmark_model,
                           const bookmarks::BookmarkNode* parent,
                           int old_index,
                           const bookmarks::BookmarkNode* node,
                           const std::set<GURL>& removed_url) override;
  void BookmarkAllUserNodesRemoved(bookmarks::BookmarkModel* bookmark_model,
                                   const std::set<GURL>& removed_urls) override;

  // BookmarkModel instance providing access to bookmarks. May be null during
  // testing but must outlive ChromeHistoryClient if non-null.
  bookmarks::BookmarkModel* bookmark_model_;
  bool is_bookmark_model_observer_;

  // Callback invoked when URLs are removed from BookmarkModel.
  base::Callback<void(const std::set<GURL>&)> on_bookmarks_removed_;

  // Subscription for notifications of changes to favicons.
  scoped_ptr<base::CallbackList<void(const std::set<GURL>&)>::Subscription>
      favicon_changed_subscription_;

  DISALLOW_COPY_AND_ASSIGN(ChromeHistoryClient);
};

#endif  // CHROME_BROWSER_HISTORY_CHROME_HISTORY_CLIENT_H_
