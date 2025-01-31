// Copyright 2015 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package org.chromium.chrome.browser.enhancedbookmarks;

import android.content.Context;
import android.support.v7.widget.RecyclerView;
import android.support.v7.widget.RecyclerView.ViewHolder;
import android.view.LayoutInflater;
import android.view.View;
import android.view.View.OnClickListener;
import android.view.View.OnLongClickListener;
import android.view.ViewGroup;
import android.widget.Checkable;

import org.chromium.base.annotations.SuppressFBWarnings;
import org.chromium.chrome.R;
import org.chromium.chrome.browser.BookmarksBridge.BookmarkItem;
import org.chromium.chrome.browser.BookmarksBridge.BookmarkModelObserver;
import org.chromium.chrome.browser.enhancedbookmarks.EnhancedBookmarkPromoHeader.PromoHeaderShowingChangeListener;
import org.chromium.components.bookmarks.BookmarkId;

import java.util.ArrayList;
import java.util.List;

/**
 * BaseAdapter for EnhancedBookmarkItemsContainer. It manages bookmarks to list there.
 */
class EnhancedBookmarkItemsAdapter extends RecyclerView.Adapter<RecyclerView.ViewHolder> implements
        EnhancedBookmarkUIObserver, PromoHeaderShowingChangeListener {

    /**
     * An abstraction for the common functionalities for {@link EnhancedBookmarkFolder} and
     * {@link EnhancedBookmarkItem}
     */
    interface BookmarkGrid extends OnClickListener, Checkable {
        /**
         * Sets the bookmarkId the object is holding. Corresponding UI changes might occur.
         */
        void setBookmarkId(BookmarkId id);

        /**
         * @return The bookmark that the object is holding.
         */
        BookmarkId getBookmarkId();
    }

    private static final int PROMO_HEADER_VIEW = 0;
    private static final int FOLDER_VIEW = 1;
    private static final int DIVIDER_VIEW = 2;
    private static final int BOOKMARK_VIEW = 3;

    private EnhancedBookmarkDelegate mDelegate;
    private Context mContext;
    private EnhancedBookmarkPromoHeader mPromoHeaderManager;

    private List<List<? extends Object>> mSections;
    private List<Object> mPromoHeaderSection = new ArrayList<>();
    private List<Object> mFolderDividerSection = new ArrayList<>();
    private List<BookmarkId> mFolderSection = new ArrayList<>();
    private List<Object> mBookmarkDividerSection = new ArrayList<>();
    private List<BookmarkId> mBookmarkSection = new ArrayList<>();

    private BookmarkModelObserver mBookmarkModelObserver = new BookmarkModelObserver() {
        @Override
        public void bookmarkNodeChanged(BookmarkItem node) {
            int position = getPositionForBookmark(node.getId());
            if (position >= 0) notifyItemChanged(position);
        }

        @Override
        public void bookmarkNodeRemoved(BookmarkItem parent, int oldIndex, BookmarkItem node,
                boolean isDoingExtensiveChanges) {
            if (node.isFolder()) {
                mDelegate.notifyStateChange(EnhancedBookmarkItemsAdapter.this);
            } else {
                int deletedPosition = getPositionForBookmark(node.getId());
                if (deletedPosition >= 0) {
                    removeItem(deletedPosition);
                }
            }
        }

        @Override
        public void bookmarkModelChanged() {
            mDelegate.notifyStateChange(EnhancedBookmarkItemsAdapter.this);
        }
    };

    EnhancedBookmarkItemsAdapter(Context context) {
        mContext = context;

        mSections = new ArrayList<>();
        mSections.add(mPromoHeaderSection);
        mSections.add(mFolderDividerSection);
        mSections.add(mFolderSection);
        mSections.add(mBookmarkDividerSection);
        mSections.add(mBookmarkSection);
    }

    BookmarkId getItem(int position) {
        return (BookmarkId) getSection(position).get(toSectionPosition(position));
    }

    private int toSectionPosition(int globalPosition) {
        int sectionPosition = globalPosition;
        for (List section : mSections) {
            if (sectionPosition < section.size()) break;
            sectionPosition -= section.size();
        }
        return sectionPosition;
    }

    private List<? extends Object> getSection(int position) {
        int i = position;
        for (List<? extends Object> section : mSections) {
            if (i < section.size()) {
                return section;
            }
            i -= section.size();
        }
        return null;
    }

    /**
     * @return The position of the given bookmark in adapter. Will return -1 if not found.
     */
    private int getPositionForBookmark(BookmarkId bookmark) {
        assert bookmark != null;
        int position = -1;
        for (int i = 0; i < getItemCount(); i++) {
            if (bookmark.equals(getItem(i))) {
                position = i;
                break;
            }
        }
        return position;
    }

    /**
     * Set folders and bookmarks to show.
     * @param folders This can be null if there is no folders to show.
     */
    private void setBookmarks(List<BookmarkId> folders, List<BookmarkId> bookmarks) {
        if (folders == null) folders = new ArrayList<BookmarkId>();

        mFolderSection.clear();
        mFolderSection.addAll(folders);
        mBookmarkSection.clear();
        mBookmarkSection.addAll(bookmarks);

        updateDividerSections();

        // TODO(kkimlabs): Animation is disabled due to a performance issue on bookmark undo.
        //                 http://crbug.com/484174
        notifyDataSetChanged();
    }

    private void updateDividerSections() {
        mFolderDividerSection.clear();
        mBookmarkDividerSection.clear();
        if (!mPromoHeaderSection.isEmpty() && !mFolderSection.isEmpty()) {
            mFolderDividerSection.add(null);
        }
        if ((!mPromoHeaderSection.isEmpty() || !mFolderSection.isEmpty())
                && !mBookmarkSection.isEmpty()) {
            mBookmarkDividerSection.add(null);
        }
    }

    private void removeItem(int position) {
        List section = getSection(position);
        assert section == mFolderSection || section == mBookmarkSection;
        section.remove(toSectionPosition(position));
        notifyItemRemoved(position);
    }

    // RecyclerView.Adapter implementation.

    @Override
    public int getItemCount() {
        int count = 0;
        for (List section : mSections) {
            count += section.size();
        }
        return count;
    }

    @Override
    public int getItemViewType(int position) {
        List section = getSection(position);

        if (section == mPromoHeaderSection) {
            return PROMO_HEADER_VIEW;
        } else if (section == mFolderDividerSection
                || section == mBookmarkDividerSection) {
            return DIVIDER_VIEW;
        } else if (section == mFolderSection) {
            return FOLDER_VIEW;
        } else if (section == mBookmarkSection) {
            return BOOKMARK_VIEW;
        }

        assert false : "Invalid position requested";
        return -1;
    }

    @Override
    public ViewHolder onCreateViewHolder(ViewGroup parent, int viewType) {
        switch (viewType) {
            case PROMO_HEADER_VIEW:
                return mPromoHeaderManager.createHolder(parent);
            case FOLDER_VIEW:
                EnhancedBookmarkFolder folder = (EnhancedBookmarkFolder) LayoutInflater.from(
                        parent.getContext()).inflate(R.layout.eb_folder, parent, false);
                folder.setDelegate(mDelegate);
                return new ItemViewHolder(folder, mDelegate);
            case DIVIDER_VIEW:
                return new ViewHolder(LayoutInflater.from(parent.getContext()).inflate(
                        R.layout.eb_divider, parent, false)) {};
            case BOOKMARK_VIEW:
                EnhancedBookmarkItem item = (EnhancedBookmarkItem) LayoutInflater.from(
                        parent.getContext()).inflate(R.layout.eb_item, parent, false);
                item.onEnhancedBookmarkDelegateInitialized(mDelegate);
                return new ItemViewHolder(item, mDelegate);
            default:
                assert false;
                return null;
        }
    }

    @SuppressFBWarnings("BC_UNCONFIRMED_CAST")
    @Override
    public void onBindViewHolder(ViewHolder holder, int position) {
        BookmarkId id = getItem(position);
        switch (getItemViewType(position)) {
            case PROMO_HEADER_VIEW:
                break;
            case FOLDER_VIEW:
                ((ItemViewHolder) holder).setBookmarkId(id);
                break;
            case DIVIDER_VIEW:
                break;
            case BOOKMARK_VIEW:
                ((ItemViewHolder) holder).setBookmarkId(id);
                break;
            default:
                assert false : "View type not supported!";
        }
    }

    // PromoHeaderShowingChangeListener implementation.

    @Override
    public void onPromoHeaderShowingChanged(boolean isShowing) {
        mPromoHeaderSection.clear();
        if (isShowing) mPromoHeaderSection.add(null);

        updateDividerSections();
        notifyDataSetChanged();
    }

    // EnhancedBookmarkUIObserver implementations.

    @Override
    public void onEnhancedBookmarkDelegateInitialized(EnhancedBookmarkDelegate delegate) {
        mDelegate = delegate;
        mDelegate.addUIObserver(this);
        mDelegate.getModel().addModelObserver(mBookmarkModelObserver);
        mPromoHeaderManager = new EnhancedBookmarkPromoHeader(mContext, this);
        if (mPromoHeaderManager.shouldShow()) mPromoHeaderSection.add(null);

        updateDividerSections();
    }

    @Override
    public void onDestroy() {
        mDelegate.removeUIObserver(this);
        mDelegate.getModel().removeModelObserver(mBookmarkModelObserver);
        mPromoHeaderManager.destroy();
    }

    @Override
    public void onAllBookmarksStateSet() {
        setBookmarks(null, mDelegate.getModel().getAllBookmarkIDsOrderedByCreationDate());
    }

    @Override
    public void onFolderStateSet(BookmarkId folder) {
        setBookmarks(mDelegate.getModel().getChildIDs(folder, true, false),
                mDelegate.getModel().getChildIDs(folder, false, true));
    }

    @Override
    public void onSelectionStateChange(List<BookmarkId> selectedBookmarks) {}

    private static class ItemViewHolder extends RecyclerView.ViewHolder implements OnClickListener,
            OnLongClickListener {
        private EnhancedBookmarkDelegate mDelegate;
        private BookmarkGrid mGrid;

        public ItemViewHolder(View view, EnhancedBookmarkDelegate delegate) {
            super(view);
            mGrid = (BookmarkGrid) view;
            mDelegate = delegate;
            view.setOnClickListener(this);
            view.setOnLongClickListener(this);
        }

        public void setBookmarkId(BookmarkId id) {
            mGrid.setBookmarkId(id);
            mGrid.setChecked(mDelegate.isBookmarkSelected(mGrid.getBookmarkId()));
        }

        @Override
        public boolean onLongClick(View v) {
            mGrid.setChecked(mDelegate.toggleSelectionForBookmark(mGrid.getBookmarkId()));
            return true;
        }

        @Override
        public void onClick(View v) {
            if (mDelegate.isSelectionEnabled()) onLongClick(v);
            else mGrid.onClick(itemView);
        }
    }

}
