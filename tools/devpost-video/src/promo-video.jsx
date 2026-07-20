import React from 'react';
import {AbsoluteFill, Audio, Composition, Sequence, Video, interpolate, staticFile, useCurrentFrame} from 'remotion';

const fps = 30;
const leadIn = 18;
const tail = 12;
const scenes = [
  ['01.wav', 6.8, 'title.png', 'Not all—or nothing.'],
  ['03.wav', 12.64, 'captures/stills/scene-02-natural-input.png', 'Enter what you know.\nKeep unknowns unknown.'],
  ['04.wav', 12.4, 'captures/stills/scene-03-climate-outlook.png', 'Climate is context—\nnot a fan-count rule.'],
  ['05.wav', 11.28, 'captures/stills/scene-04-current-barn.png', '10-fan gap\n30 cows uncovered — estimated'],
  ['06.wav', 11.04, 'captures/stills/scene-05-two-horizons.png', 'Protect today’s herd.\nAvoid overbuilding for tomorrow.'],
  ['07.wav', 11.76, 'captures/stills/scene-06-comparison-switch.png', 'Current → Phase 1 → Full build-out'],
  ['08.wav', 14.08, 'captures/stills/scene-07-financial-screening.png', 'Annual burden screening—\nnot total farm profit'],
  ['09.wav', 9.84, 'captures/stills/scene-08-next-step.png', 'What can we do now?\nWhat should we measure next?'],
  ['10.wav', 13.68, 'captures/stills/scene-09-barn-background.png', 'GPT-5.6\nInput and explanation\n\nPYTHON\nCalculations and classifications\n\nCODEX\nImplementation and tests'],
];
const duration = (scene) => Math.ceil(scene[1] * fps) + tail;
const totalFrames = scenes.reduce((sum, scene) => sum + duration(scene), 0);
const timedScenes = scenes.reduce((items, scene) => {
  const from = items.length === 0 ? 0 : items[items.length - 1].from + items[items.length - 1].durationInFrames;
  items.push({scene, from, durationInFrames: duration(scene)});
  return items;
}, []);

const Caption = ({children}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return <div style={{position: 'absolute', bottom: 42, left: 0, right: 0, display: 'flex', justifyContent: 'center', opacity, pointerEvents: 'none'}}><div style={{textAlign: 'center', color: '#fff', backgroundColor: 'rgba(18, 24, 28, 0.78)', borderRadius: 18, padding: '16px 28px', fontFamily: 'Arial, sans-serif', fontWeight: 700, fontSize: 42, lineHeight: 1.2, whiteSpace: 'pre-line', boxShadow: '0 3px 12px rgba(0,0,0,.5)'}}>{children}</div></div>;
};

const Scene = ({scene, index, sceneStart}) => {
  const frame = useCurrentFrame();
  const source = staticFile(scene[2]);
  const zoom = index === 0 ? interpolate(frame, [0, duration(scene)], [1, 1.025]) : 1;
  const style = {
    width: index === 0 ? 1920 : 1280,
    height: 1080,
    objectFit: 'contain',
    transform: `scale(${zoom})`,
  };
  const switchFrames = index === 1 ? [
    'captures/stills/scene-02-before-submit.png',
    'captures/stills/scene-02-candidate-confirmation.png',
  ] : index === 7 ? [
    'captures/stills/scene-08-next-step-current.png',
    'captures/stills/scene-08-next-step-first-phase.png',
    'captures/stills/scene-08-next-step-full-coverage.png',
  ] : null;
  const switchFrame = index === 1
    ? (15 * fps) - sceneStart
    : Math.ceil(duration(scene) / (switchFrames?.length ?? 1));
  const switchedSource = switchFrames ? staticFile(switchFrames[Math.min(switchFrames.length - 1, Math.floor(frame / switchFrame))]) : null;
  const switchAt = Math.floor(duration(scene) / 2);
  const finalBlackAt = Math.max(0, (103 * fps) - sceneStart);
  const transitionOpacity = interpolate(frame, [finalBlackAt, finalBlackAt + 18], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const closingOpacity = interpolate(frame, [finalBlackAt, finalBlackAt + 18], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const visualStyle = index === 8 ? {...style, opacity: transitionOpacity} : style;
  return (
    <AbsoluteFill style={{backgroundColor: '#000', justifyContent: 'center', alignItems: 'center', overflow: 'hidden'}}>
      {index === 5 ? <img src={staticFile(frame < switchAt ? 'captures/stills/scene-09-comparison-first-phase.png' : 'captures/stills/scene-09-comparison-full-coverage.png')} style={style} /> : switchFrames ? <img src={switchedSource} style={visualStyle} /> : scene[2].endsWith('.webm') ? <Video src={source} startFrom={scene[4] ?? 0} loop style={visualStyle} /> : <img src={source} style={visualStyle} />}
      {index === 8 ? <>
        <div style={{position: 'absolute', inset: 0, backgroundColor: '#000', opacity: 0.52 * transitionOpacity}} />
        <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: '#fff', fontFamily: 'Arial, sans-serif', fontWeight: 700, fontSize: 52, lineHeight: 1.25, whiteSpace: 'pre-line', opacity: transitionOpacity, textShadow: '0 3px 14px #000'}}>{scene[3]}</div>
        <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: '#fff', fontFamily: 'Arial, sans-serif', fontWeight: 700, fontSize: 120, lineHeight: 1.1, opacity: closingOpacity}}>Measure first.<br />Invest in phases.</div>
      </> : null}
      <Sequence from={leadIn}>
        <Audio src={staticFile(`voices_stereo/${scene[0]}`)} />
        {index !== 8 ? <Caption>{scene[3]}</Caption> : null}
        </Sequence>
    </AbsoluteFill>
  );
};

const Timeline = () => <AbsoluteFill>{timedScenes.map(({scene, from, durationInFrames}, index) => <Sequence key={scene[0]} from={from} durationInFrames={durationInFrames}><Scene scene={scene} index={index} sceneStart={from} /></Sequence>)}</AbsoluteFill>;

export const PromoVideo = () => <Composition id="DairyHorizonPromo" component={Timeline} durationInFrames={totalFrames} fps={fps} width={1920} height={1080} />;
