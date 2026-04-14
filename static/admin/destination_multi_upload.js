(function () {
  function initDestinationMultiUpload() {
    var addBtn = document.getElementById('dest-add-images-btn');
    var fileInput = document.getElementById('id_new_images');
    var previewGrid = document.getElementById('dest-staged-preview');

    if (!addBtn || !fileInput || !previewGrid) {
      return;
    }

    var accumulatedFiles = [];

    // Click the styled button → trigger hidden file input
    addBtn.addEventListener('click', function () {
      fileInput.click();
    });

    // Hover effect
    addBtn.addEventListener('mouseenter', function () {
      addBtn.style.background = '#0ea5e9';
      addBtn.style.color = '#fff';
      addBtn.style.borderColor = '#0ea5e9';
    });
    addBtn.addEventListener('mouseleave', function () {
      addBtn.style.background = '#e0f2fe';
      addBtn.style.color = '#0369a1';
      addBtn.style.borderColor = '#0ea5e9';
    });

    function syncFilesToInput() {
      var dt = new DataTransfer();
      accumulatedFiles.forEach(function (file) {
        dt.items.add(file);
      });
      fileInput.files = dt.files;
    }

    function renderPreview() {
      previewGrid.innerHTML = '';

      if (!accumulatedFiles.length) {
        return;
      }

      // Label
      var label = document.createElement('div');
      label.style.width = '100%';
      label.style.fontSize = '12px';
      label.style.fontWeight = '700';
      label.style.color = '#0369a1';
      label.style.marginBottom = '4px';
      label.textContent = 'Staged for upload (' + accumulatedFiles.length + ' image' + (accumulatedFiles.length > 1 ? 's' : '') + ') — will be saved when you click Save:';
      previewGrid.appendChild(label);

      accumulatedFiles.forEach(function (file, index) {
        if (!file.type || file.type.indexOf('image/') !== 0) {
          return;
        }

        var card = document.createElement('div');
        card.style.cssText = 'width:130px; border:2px dashed #0ea5e9; border-radius:8px; padding:6px; background:#f0f9ff; position:relative;';

        var img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        img.alt = file.name;
        img.style.cssText = 'width:100%; height:80px; object-fit:cover; border-radius:4px;';
        img.onload = function () { URL.revokeObjectURL(img.src); };

        var caption = document.createElement('div');
        caption.style.cssText = 'margin-top:4px; font-size:11px; color:#57606a; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;';
        caption.textContent = file.name;

        var removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.textContent = '×';
        removeBtn.title = 'Remove';
        removeBtn.style.cssText = 'position:absolute; top:2px; right:2px; width:20px; height:20px; border:none; border-radius:50%; background:rgba(220,38,38,0.85); color:#fff; font-size:14px; line-height:1; cursor:pointer; display:flex; align-items:center; justify-content:center;';
        removeBtn.addEventListener('click', function () {
          accumulatedFiles.splice(index, 1);
          syncFilesToInput();
          renderPreview();
        });

        card.appendChild(removeBtn);
        card.appendChild(img);
        card.appendChild(caption);
        previewGrid.appendChild(card);
      });
    }

    fileInput.addEventListener('change', function () {
      var newFiles = Array.prototype.slice.call(fileInput.files || []);
      newFiles.forEach(function (file) {
        accumulatedFiles.push(file);
      });
      syncFilesToInput();
      renderPreview();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDestinationMultiUpload);
  } else {
    initDestinationMultiUpload();
  }
})();
