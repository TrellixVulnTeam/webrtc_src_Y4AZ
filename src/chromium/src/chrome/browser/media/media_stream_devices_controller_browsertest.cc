// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include <string>

#include "base/bind.h"
#include "base/prefs/pref_service.h"
#include "chrome/browser/content_settings/tab_specific_content_settings.h"
#include "chrome/browser/media/media_capture_devices_dispatcher.h"
#include "chrome/browser/media/media_stream_capture_indicator.h"
#include "chrome/browser/media/media_stream_device_permissions.h"
#include "chrome/browser/media/media_stream_devices_controller.h"
#include "chrome/browser/media/webrtc_browsertest_base.h"
#include "chrome/browser/profiles/profile.h"
#include "chrome/browser/ui/browser.h"
#include "chrome/browser/ui/tabs/tab_strip_model.h"
#include "chrome/common/pref_names.h"
#include "chrome/test/base/ui_test_utils.h"
#include "components/content_settings/core/browser/host_content_settings_map.h"
#include "content/public/common/media_stream_request.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace {

// Causes the controller to update the TabSpecificContentSettings associated
// with the same WebContents with the current permissions. This should be the
// last change made to the controller in the test.
void NotifyTabSpecificContentSettings(
    MediaStreamDevicesController* controller) {
  // Note that calling Deny() would have the same effect of passing the current
  // permissions state to the TabSpecificContentSettings. Deny() and Accept()
  // differ in their effect on the controller itself, but that is not important
  // in the tests calling this.
  if (controller->IsAskingForAudio() || controller->IsAskingForVideo())
    controller->PermissionGranted();
}

}  // namespace

class MediaStreamDevicesControllerTest : public WebRtcTestBase {
 public:
  MediaStreamDevicesControllerTest()
      : example_url_("https://www.example.com"),
        example_audio_id_("fake_dev"),
        example_video_id_("fake_dev"),
        media_stream_result_(content::NUM_MEDIA_REQUEST_RESULTS) {}

  // Dummy callback for when we deny the current request directly.
  void OnMediaStreamResponse(const content::MediaStreamDevices& devices,
                             content::MediaStreamRequestResult result,
                             scoped_ptr<content::MediaStreamUI> ui) {
    media_stream_devices_ = devices;
    media_stream_result_ = result;
  }

 protected:
  enum DeviceType { DEVICE_TYPE_AUDIO, DEVICE_TYPE_VIDEO };
  enum Access { ACCESS_ALLOWED, ACCESS_DENIED };

  const GURL& example_url() const { return example_url_; }

  TabSpecificContentSettings* GetContentSettings() {
    return TabSpecificContentSettings::FromWebContents(GetWebContents());
  }

  const std::string& example_audio_id() const { return example_audio_id_; }
  const std::string& example_video_id() const { return example_video_id_; }

  content::MediaStreamRequestResult media_stream_result() const {
    return media_stream_result_;
  }

  // Sets the device policy-controlled |access| for |example_url_| to be for the
  // selected |device_type|.
  void SetDevicePolicy(DeviceType device_type, Access access) {
    PrefService* prefs = Profile::FromBrowserContext(
        GetWebContents()->GetBrowserContext())->GetPrefs();
    const char* policy_name = NULL;
    switch (device_type) {
      case DEVICE_TYPE_AUDIO:
        policy_name = prefs::kAudioCaptureAllowed;
        break;
      case DEVICE_TYPE_VIDEO:
        policy_name = prefs::kVideoCaptureAllowed;
        break;
    }
    prefs->SetBoolean(policy_name, access == ACCESS_ALLOWED);
  }

  // Set the content settings for mic/cam.
  void SetContentSettings(ContentSetting mic_setting,
                          ContentSetting cam_setting) {
    HostContentSettingsMap* content_settings =
        Profile::FromBrowserContext(GetWebContents()->GetBrowserContext())
            ->GetHostContentSettingsMap();
    ContentSettingsPattern pattern =
        ContentSettingsPattern::FromURLNoWildcard(example_url_);
    content_settings->SetContentSetting(pattern, pattern,
                                        CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC,
                                        std::string(), mic_setting);
    content_settings->SetContentSetting(
        pattern, pattern, CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA,
        std::string(), cam_setting);
  }

  // Checks whether the devices returned in OnMediaStreamResponse contains a
  // microphone and/or camera device.
  bool DevicesContains(bool needs_mic, bool needs_cam) {
    bool has_mic = false;
    bool has_cam = false;
    for (const auto& device : media_stream_devices_) {
      if (device.type == content::MEDIA_DEVICE_AUDIO_CAPTURE)
        has_mic = true;
      if (device.type == content::MEDIA_DEVICE_VIDEO_CAPTURE)
        has_cam = true;
    }

    return needs_mic == has_mic && needs_cam == has_cam;
  }

  content::WebContents* GetWebContents() {
    return browser()->tab_strip_model()->GetActiveWebContents();
  }

  // Creates a MediaStreamRequest, asking for those media types, which have a
  // non-empty id string.
  content::MediaStreamRequest CreateRequest(const std::string& audio_id,
                                            const std::string& video_id) {
    content::MediaStreamType audio_type =
        audio_id.empty() ? content::MEDIA_NO_SERVICE
                         : content::MEDIA_DEVICE_AUDIO_CAPTURE;
    content::MediaStreamType video_type =
        video_id.empty() ? content::MEDIA_NO_SERVICE
                         : content::MEDIA_DEVICE_VIDEO_CAPTURE;
    return content::MediaStreamRequest(0,
                                       0,
                                       0,
                                       example_url(),
                                       false,
                                       content::MEDIA_DEVICE_ACCESS,
                                       audio_id,
                                       video_id,
                                       audio_type,
                                       video_type);
  }

 private:
  void SetUpOnMainThread() override {
    WebRtcTestBase::SetUpOnMainThread();

    // Cleanup.
    media_stream_devices_.clear();
    media_stream_result_ = content::NUM_MEDIA_REQUEST_RESULTS;

    content::MediaStreamDevices audio_devices;
    content::MediaStreamDevice fake_audio_device(
        content::MEDIA_DEVICE_AUDIO_CAPTURE, example_audio_id_,
        "Fake Audio Device");
    audio_devices.push_back(fake_audio_device);
    MediaCaptureDevicesDispatcher::GetInstance()->SetTestAudioCaptureDevices(
        audio_devices);

    content::MediaStreamDevices video_devices;
    content::MediaStreamDevice fake_video_device(
        content::MEDIA_DEVICE_VIDEO_CAPTURE, example_video_id_,
        "Fake Video Device");
    video_devices.push_back(fake_video_device);
    MediaCaptureDevicesDispatcher::GetInstance()->SetTestVideoCaptureDevices(
        video_devices);

    ui_test_utils::NavigateToURL(browser(), example_url_);

    EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_CAMERA_NOT_ACCESSED,
              GetContentSettings()->GetMicrophoneCameraState());
  }

  const GURL example_url_;
  const std::string example_audio_id_;
  const std::string example_video_id_;

  content::MediaStreamDevices media_stream_devices_;
  content::MediaStreamRequestResult media_stream_result_;
};

// Request and allow microphone access.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest, RequestAndAllowMic) {
  SetDevicePolicy(DEVICE_TYPE_AUDIO, ACCESS_ALLOWED);
  MediaStreamDevicesController controller(
      GetWebContents(), CreateRequest(example_audio_id(), std::string()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&controller);

  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_ACCESSED,
            GetContentSettings()->GetMicrophoneCameraState());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());
  EXPECT_EQ(std::string(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(std::string(),
            GetContentSettings()->media_stream_selected_video_device());
}

// Request and allow camera access.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest, RequestAndAllowCam) {
  SetDevicePolicy(DEVICE_TYPE_VIDEO, ACCESS_ALLOWED);
  MediaStreamDevicesController controller(
      GetWebContents(), CreateRequest(std::string(), example_video_id()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&controller);

  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(TabSpecificContentSettings::CAMERA_ACCESSED,
            GetContentSettings()->GetMicrophoneCameraState());
  EXPECT_EQ(std::string(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(std::string(),
            GetContentSettings()->media_stream_selected_audio_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());
}

// Request and block microphone access.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest, RequestAndBlockMic) {
  SetDevicePolicy(DEVICE_TYPE_AUDIO, ACCESS_DENIED);
  MediaStreamDevicesController controller(
      GetWebContents(), CreateRequest(example_audio_id(), std::string()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&controller);

  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_ACCESSED |
                TabSpecificContentSettings::MICROPHONE_BLOCKED,
            GetContentSettings()->GetMicrophoneCameraState());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());
  EXPECT_EQ(std::string(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(std::string(),
            GetContentSettings()->media_stream_selected_video_device());
}

// Request and block camera access.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest, RequestAndBlockCam) {
  SetDevicePolicy(DEVICE_TYPE_VIDEO, ACCESS_DENIED);
  MediaStreamDevicesController controller(
      GetWebContents(), CreateRequest(std::string(), example_video_id()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&controller);

  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(TabSpecificContentSettings::CAMERA_ACCESSED |
                TabSpecificContentSettings::CAMERA_BLOCKED,
            GetContentSettings()->GetMicrophoneCameraState());
  EXPECT_EQ(std::string(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(std::string(),
            GetContentSettings()->media_stream_selected_audio_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());
}

// Request and allow microphone and camera access.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest,
                       RequestAndAllowMicCam) {
  SetDevicePolicy(DEVICE_TYPE_AUDIO, ACCESS_ALLOWED);
  SetDevicePolicy(DEVICE_TYPE_VIDEO, ACCESS_ALLOWED);
  MediaStreamDevicesController controller(
      GetWebContents(), CreateRequest(example_audio_id(), example_video_id()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&controller);

  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_ACCESSED |
                TabSpecificContentSettings::CAMERA_ACCESSED,
            GetContentSettings()->GetMicrophoneCameraState());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());
}

// Request and block microphone and camera access.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest,
                       RequestAndBlockMicCam) {
  SetDevicePolicy(DEVICE_TYPE_AUDIO, ACCESS_DENIED);
  SetDevicePolicy(DEVICE_TYPE_VIDEO, ACCESS_DENIED);
  MediaStreamDevicesController controller(
      GetWebContents(), CreateRequest(example_audio_id(), example_video_id()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&controller);

  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_ACCESSED |
                TabSpecificContentSettings::MICROPHONE_BLOCKED |
                TabSpecificContentSettings::CAMERA_ACCESSED |
                TabSpecificContentSettings::CAMERA_BLOCKED,
            GetContentSettings()->GetMicrophoneCameraState());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());
}

// Request microphone and camera access. Allow microphone, block camera.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest,
                       RequestMicCamBlockCam) {
  SetDevicePolicy(DEVICE_TYPE_AUDIO, ACCESS_ALLOWED);
  SetDevicePolicy(DEVICE_TYPE_VIDEO, ACCESS_DENIED);
  MediaStreamDevicesController controller(
      GetWebContents(), CreateRequest(example_audio_id(), example_video_id()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&controller);

  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_ACCESSED |
                TabSpecificContentSettings::CAMERA_ACCESSED |
                TabSpecificContentSettings::CAMERA_BLOCKED,
            GetContentSettings()->GetMicrophoneCameraState());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());
}

// Request microphone and camera access. Block microphone, allow camera.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest,
                       RequestMicCamBlockMic) {
  SetDevicePolicy(DEVICE_TYPE_AUDIO, ACCESS_DENIED);
  SetDevicePolicy(DEVICE_TYPE_VIDEO, ACCESS_ALLOWED);
  MediaStreamDevicesController controller(
      GetWebContents(), CreateRequest(example_audio_id(), example_video_id()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&controller);

  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_ACCESSED |
                TabSpecificContentSettings::MICROPHONE_BLOCKED |
                TabSpecificContentSettings::CAMERA_ACCESSED,
            GetContentSettings()->GetMicrophoneCameraState());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());
}

// Request microphone access. Requesting camera should not change microphone
// state.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest,
                       RequestCamDoesNotChangeMic) {
  // Request mic and deny.
  SetDevicePolicy(DEVICE_TYPE_AUDIO, ACCESS_DENIED);
  MediaStreamDevicesController mic_controller(
      GetWebContents(), CreateRequest(example_audio_id(), std::string()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&mic_controller);
  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());

  // Request cam and allow
  SetDevicePolicy(DEVICE_TYPE_VIDEO, ACCESS_ALLOWED);
  MediaStreamDevicesController cam_controller(
      GetWebContents(), CreateRequest(std::string(), example_video_id()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&cam_controller);
  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());

  // Mic state should not have changed.
  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());
}

// Denying mic access after camera access should still show the camera as state.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest,
                       DenyMicDoesNotChangeCam) {
  // Request cam and allow
  SetDevicePolicy(DEVICE_TYPE_VIDEO, ACCESS_ALLOWED);
  MediaStreamDevicesController cam_controller(
      GetWebContents(), CreateRequest(std::string(), example_video_id()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&cam_controller);
  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());
  EXPECT_EQ(TabSpecificContentSettings::CAMERA_ACCESSED,
            GetContentSettings()->GetMicrophoneCameraState());

  // Simulate that an a video stream is now being captured.
  content::MediaStreamDevice fake_video_device(
      content::MEDIA_DEVICE_VIDEO_CAPTURE, example_video_id(),
      example_video_id());
  content::MediaStreamDevices video_devices(1, fake_video_device);
  MediaCaptureDevicesDispatcher* dispatcher =
      MediaCaptureDevicesDispatcher::GetInstance();
  dispatcher->SetTestVideoCaptureDevices(video_devices);
  scoped_ptr<content::MediaStreamUI> video_stream_ui =
      dispatcher->GetMediaStreamCaptureIndicator()->
          RegisterMediaStream(GetWebContents(), video_devices);
  video_stream_ui->OnStarted(base::Closure());

  // Request mic and deny.
  SetDevicePolicy(DEVICE_TYPE_AUDIO, ACCESS_DENIED);
  MediaStreamDevicesController mic_controller(
      GetWebContents(), CreateRequest(example_audio_id(), std::string()),
      base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                 this));
  NotifyTabSpecificContentSettings(&mic_controller);
  EXPECT_FALSE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_TRUE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_MIC));
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_requested_audio_device());
  EXPECT_EQ(example_audio_id(),
            GetContentSettings()->media_stream_selected_audio_device());

  // Cam should still be included in the state.
  EXPECT_TRUE(GetContentSettings()->IsContentAllowed(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_FALSE(GetContentSettings()->IsContentBlocked(
      CONTENT_SETTINGS_TYPE_MEDIASTREAM_CAMERA));
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_requested_video_device());
  EXPECT_EQ(example_video_id(),
            GetContentSettings()->media_stream_selected_video_device());
  EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_ACCESSED |
                TabSpecificContentSettings::MICROPHONE_BLOCKED |
                TabSpecificContentSettings::CAMERA_ACCESSED,
            GetContentSettings()->GetMicrophoneCameraState());

  // After ending the camera capture, the camera permission is no longer
  // relevant, so it should no be included in the mic/cam state.
  video_stream_ui.reset();
  EXPECT_EQ(TabSpecificContentSettings::MICROPHONE_ACCESSED |
                TabSpecificContentSettings::MICROPHONE_BLOCKED,
            GetContentSettings()->GetMicrophoneCameraState());
}

// Stores the ContentSettings inputs for a particular test and has functions
// which return the expected outputs for that test.
struct ContentSettingsTestData {
  // The initial value of the mic/cam content settings.
  ContentSetting mic;
  ContentSetting cam;
  // Whether the infobar should be accepted if it's shown.
  bool accept_infobar;

  // Whether the infobar should be displayed to request mic/cam for the given
  // content settings inputs.
  bool ExpectMicInfobar() const { return mic == CONTENT_SETTING_ASK; }
  bool ExpectCamInfobar() const { return cam == CONTENT_SETTING_ASK; }

  // Whether or not the mic/cam should be allowed after clicking accept/deny for
  // the given inputs.
  bool ExpectMicAllowed() const {
    return mic == CONTENT_SETTING_ALLOW ||
           (mic == CONTENT_SETTING_ASK && accept_infobar);
  }
  bool ExpectCamAllowed() const {
    return cam == CONTENT_SETTING_ALLOW ||
           (cam == CONTENT_SETTING_ASK && accept_infobar);
  }

  // The expected media stream result after clicking accept/deny for the given
  // inputs.
  content::MediaStreamRequestResult ExpectedMediaStreamResult() const {
    if (ExpectMicAllowed() || ExpectCamAllowed())
      return content::MEDIA_DEVICE_OK;
    return content::MEDIA_DEVICE_PERMISSION_DENIED;
  }
};

// Test all combinations of cam/mic content settings. Then tests the result of
// clicking both accept/deny on the infobar. Both cam/mic are requested.
IN_PROC_BROWSER_TEST_F(MediaStreamDevicesControllerTest, ContentSettings) {
  static const ContentSettingsTestData tests[] = {
      // Settings that won't result in an infobar.
      {CONTENT_SETTING_ALLOW, CONTENT_SETTING_ALLOW, false},
      {CONTENT_SETTING_ALLOW, CONTENT_SETTING_BLOCK, false},
      {CONTENT_SETTING_BLOCK, CONTENT_SETTING_ALLOW, false},
      {CONTENT_SETTING_BLOCK, CONTENT_SETTING_BLOCK, false},

      // Settings that will result in an infobar. Test both accept and deny.
      {CONTENT_SETTING_ALLOW, CONTENT_SETTING_ASK, false},
      {CONTENT_SETTING_ALLOW, CONTENT_SETTING_ASK, true},

      {CONTENT_SETTING_ASK, CONTENT_SETTING_ASK, false},
      {CONTENT_SETTING_ASK, CONTENT_SETTING_ASK, true},

      {CONTENT_SETTING_BLOCK, CONTENT_SETTING_ASK, false},
      {CONTENT_SETTING_BLOCK, CONTENT_SETTING_ASK, true},

      {CONTENT_SETTING_ASK, CONTENT_SETTING_ALLOW, false},
      {CONTENT_SETTING_ASK, CONTENT_SETTING_ALLOW, true},

      {CONTENT_SETTING_ASK, CONTENT_SETTING_BLOCK, false},
      {CONTENT_SETTING_ASK, CONTENT_SETTING_BLOCK, true},
  };

  for (auto& test : tests) {
    SetContentSettings(test.mic, test.cam);
    MediaStreamDevicesController controller(
        GetWebContents(), CreateRequest(example_audio_id(), example_video_id()),
        base::Bind(&MediaStreamDevicesControllerTest::OnMediaStreamResponse,
                   this));

    // Check that the infobar is requesting the expected cam/mic values.
    ASSERT_EQ(test.ExpectMicInfobar(), controller.IsAskingForAudio());
    ASSERT_EQ(test.ExpectCamInfobar(), controller.IsAskingForVideo());

    // Accept or deny the infobar if it's showing.
    if (test.ExpectMicInfobar() || test.ExpectCamInfobar()) {
      if (test.accept_infobar)
        controller.PermissionGranted();
      else
        controller.PermissionDenied();
    }

    // Check the media stream result is expected and the devices returned are
    // expected;
    ASSERT_EQ(test.ExpectedMediaStreamResult(), media_stream_result());
    ASSERT_TRUE(
        DevicesContains(test.ExpectMicAllowed(), test.ExpectCamAllowed()));
  }
}
