package android.print;

import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;

import java.io.File;

/**
 * Writes the print adapter of a WebView to a PDF file without the print dialog (Browser menu > Save page as...).
 * It lives in the android.print package because LayoutResultCallback and WriteResultCallback can only be
 * subclassed from there.
 */
public class PdfPrint {
    public interface Done {
        void finished(boolean ok, String error);
    }

    public static void save(final PrintDocumentAdapter adapter, final File file, final Done done) {
        PrintAttributes attrs = new PrintAttributes.Builder()
            .setMediaSize(PrintAttributes.MediaSize.ISO_A4)
            .setResolution(new PrintAttributes.Resolution("pdf", "pdf", 300, 300))
            .setMinMargins(PrintAttributes.Margins.NO_MARGINS)
            .build();
        adapter.onStart();
        adapter.onLayout(null, attrs, new CancellationSignal(), new PrintDocumentAdapter.LayoutResultCallback() {
            @Override
            public void onLayoutFinished(PrintDocumentInfo info, boolean changed) {
                try {
                    final ParcelFileDescriptor fd = ParcelFileDescriptor.open(file,
                        ParcelFileDescriptor.MODE_READ_WRITE | ParcelFileDescriptor.MODE_CREATE
                            | ParcelFileDescriptor.MODE_TRUNCATE);
                    adapter.onWrite(new PageRange[]{PageRange.ALL_PAGES}, fd, new CancellationSignal(),
                        new PrintDocumentAdapter.WriteResultCallback() {
                            @Override
                            public void onWriteFinished(PageRange[] pages) {
                                try { fd.close(); } catch (Exception e) { }
                                adapter.onFinish();
                                done.finished(true, "");
                            }

                            @Override
                            public void onWriteFailed(CharSequence error) {
                                try { fd.close(); } catch (Exception e) { }
                                adapter.onFinish();
                                done.finished(false, String.valueOf(error));
                            }
                        });
                } catch (Exception e) {
                    done.finished(false, String.valueOf(e));
                }
            }

            @Override
            public void onLayoutFailed(CharSequence error) {
                done.finished(false, String.valueOf(error));
            }
        }, null);
    }
}
