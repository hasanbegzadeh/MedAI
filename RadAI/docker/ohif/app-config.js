window.config = {
  routerBasename: '/',
  showStudyList: true,
  extensions: [],
  modes: [],

  defaultDataSourceName: 'dicomweb',

  dataSources: [
    {
      namespace: '@ohif/extension-default.dataSourcesModule.dicomweb',
      sourceName: 'dicomweb',
      configuration: {
        friendlyName: 'RadAI Orthanc',
        name: 'orthanc',
        wadoUriRoot: '/orthanc/wado',
        qidoRoot: '/orthanc/dicom-web',
        wadoRoot: '/orthanc/dicom-web',
        qidoSupportsIncludeField: true,
        imageRendering: 'wadors',
        thumbnailRendering: 'wadors',
        enableStudyLazyLoad: true,
        supportsFuzzyMatching: true,
        supportsWildcard: true,
        singlepart: 'bulkdata,video',
        requestTransferSyntaxUID: '1.2.840.10008.1.2.4.202',
        acceptHeader: [
          'multipart/related; type="application/octet-stream"; transfer-syntax=*',
        ],
        headers: {
          Authorization: 'Basic ' + btoa('orthanc:' + (window.__ORTHANC_PASSWORD__ || 'orthanc')),
        },
      },
    },
  ],

  // RadAI Backend API
  customizationService: {
    '@ohif/customization-service.globalSidePanel': {
      rightPanels: [
        '@ohif/extension-cornerstone-dicom-sr.panelModule.panelSRSeriesList',
        '@ohif/extension-default.panelModule.measure',
      ],
    },
  },

  hotkeys: [
    { commandName: 'incrementActiveViewport', label: 'Next Viewport', keys: ['right'] },
    { commandName: 'decrementActiveViewport', label: 'Prev Viewport', keys: ['left'] },
    { commandName: 'rotateViewportCW', label: 'Rotate Right', keys: ['r'] },
    { commandName: 'rotateViewportCCW', label: 'Rotate Left', keys: ['l'] },
    { commandName: 'invertViewport', label: 'Invert', keys: ['i'] },
    { commandName: 'flipViewportHorizontal', label: 'Flip Horizontal', keys: ['h'] },
    { commandName: 'flipViewportVertical', label: 'Flip Vertical', keys: ['v'] },
    { commandName: 'scaleUpViewport', label: 'Zoom In', keys: ['+'] },
    { commandName: 'scaleDownViewport', label: 'Zoom Out', keys: ['-'] },
    { commandName: 'fitViewportToWindow', label: 'Fit to Window', keys: ['='] },
    { commandName: 'resetViewport', label: 'Reset', keys: ['space'] },
    { commandName: 'nextImage', label: 'Next Image', keys: ['down'] },
    { commandName: 'previousImage', label: 'Previous Image', keys: ['up'] },
  ],
};
