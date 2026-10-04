#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 4) return 2;
        NSURL *videoURL = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]];
        NSURL *audioURL = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[2]]];
        NSURL *outputURL = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[3]]];
        AVURLAsset *videoAsset = [AVURLAsset URLAssetWithURL:videoURL options:nil];
        AVURLAsset *audioAsset = [AVURLAsset URLAssetWithURL:audioURL options:nil];
        AVMutableComposition *composition = [AVMutableComposition composition];
        AVAssetTrack *sourceVideo = [[videoAsset tracksWithMediaType:AVMediaTypeVideo] firstObject];
        AVMutableCompositionTrack *targetVideo = [composition addMutableTrackWithMediaType:AVMediaTypeVideo preferredTrackID:kCMPersistentTrackID_Invalid];
        NSError *error = nil;
        CMTime duration = videoAsset.duration;
        if (![targetVideo insertTimeRange:CMTimeRangeMake(kCMTimeZero, duration) ofTrack:sourceVideo atTime:kCMTimeZero error:&error]) return 3;
        targetVideo.preferredTransform = sourceVideo.preferredTransform;
        AVAssetTrack *sourceAudio = [[audioAsset tracksWithMediaType:AVMediaTypeAudio] firstObject];
        AVMutableCompositionTrack *targetAudio = [composition addMutableTrackWithMediaType:AVMediaTypeAudio preferredTrackID:kCMPersistentTrackID_Invalid];
        if (![targetAudio insertTimeRange:CMTimeRangeMake(kCMTimeZero, duration) ofTrack:sourceAudio atTime:kCMTimeZero error:&error]) return 4;
        [[NSFileManager defaultManager] removeItemAtURL:outputURL error:nil];
        AVAssetExportSession *exporter = [[AVAssetExportSession alloc] initWithAsset:composition presetName:AVAssetExportPresetHighestQuality];
        exporter.outputURL = outputURL;
        exporter.outputFileType = AVFileTypeMPEG4;
        exporter.shouldOptimizeForNetworkUse = YES;
        dispatch_semaphore_t sem = dispatch_semaphore_create(0);
        [exporter exportAsynchronouslyWithCompletionHandler:^{ dispatch_semaphore_signal(sem); }];
        dispatch_semaphore_wait(sem, DISPATCH_TIME_FOREVER);
        if (exporter.status != AVAssetExportSessionStatusCompleted) {
            fprintf(stderr, "%s\n", exporter.error.localizedDescription.UTF8String ?: "export failed"); return 5;
        }
        printf("%s\n", outputURL.path.UTF8String);
    }
    return 0;
}
