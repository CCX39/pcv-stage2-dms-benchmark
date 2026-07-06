import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader';
import attributes from 'three/src/renderers/common/Attributes.js';
import * as THREE from 'three'

// 全局开关, true开启打印，false关闭打印
const ENABLE_LOGGING = false;
// 保存原始的 console.log
const originalConsoleLog = console.log;
console.log = function (...args) {
  if (ENABLE_LOGGING) originalConsoleLog.apply(console, args);
};

let PLYTimes = [];

self.onmessage = async function (event) {

  const { data, cellKey, cellId, frameId, transMode } = event.data;
  let result = null;
  try {
    let finalResult; // 用于存储最终要发送的 result 对象

    if (transMode === 1 || transMode === 'ply') {
      // parsePLY 现在返回包含 geometryData 和 decodeTime 的对象
      const plyParseResult = self.parsePLY(frameId, cellId, data, cellKey); // 传递 cellId
      // 构建发送回主线程的 result 结构
      finalResult = {
        ...plyParseResult.geometryData, // 包含 frame_id, cell_id, positions, colors, normals
        decodeTime: plyParseResult.decodeTime // decodeTime 为 -1
      };

    } else if (transMode === 2 || transMode === 'drc') {
      // decodeDRC 现在返回包含 geometryData 和 decodeTime 的对象
      const drcDecodeResult = await self.decodeDRC(frameId, cellId, data, cellKey);
      // 构建发送回主线程的 result 结构
      finalResult = {
        ...drcDecodeResult.geometryData, // 包含 frame_id, cell_id, positions, colors, normals
        decodeTime: drcDecodeResult.decodeTime // 实际的解码时间
      };
    } else {
      // 如果有未知的 transMode
      throw new Error(`Unknown transMode: ${transMode}`);
    }

    // --- 新代码：准备要转移的对象 ---
    const transferableObjects = [];
    if (finalResult.positions && finalResult.positions.buffer) {
      transferableObjects.push(finalResult.positions.buffer);
    }
    if (finalResult.colors && finalResult.colors.buffer) {
      // 避免重复添加同一个 buffer (虽然不太可能发生)
      if (!transferableObjects.includes(finalResult.colors.buffer)) {
        transferableObjects.push(finalResult.colors.buffer);
      }
    }
    if (finalResult.normals && finalResult.normals.buffer) {
      if (!transferableObjects.includes(finalResult.normals.buffer)) {
        transferableObjects.push(finalResult.normals.buffer);
      }
    }

    // 成功时发送 result 消息
    self.postMessage({
      result: finalResult, // 直接发送构建好的 result 对象
      cellKey: cellKey
    }, transferableObjects);

  } catch (error) {
    // 失败时发送 error 消息
    console.error(`Error processing ${cellKey} in worker:`, error); // 在 worker 中也打印错误详情
    self.postMessage({
      error: `Worker error for ${cellKey}: ${error.message || error}`, // 包含 cellKey 和错误消息
      cellKey: cellKey
    });
  }
};

self.parsePLY = function (frame_id, cell_id, ply_data, ply_cellKey) {
  PLYTimes[ply_cellKey] = performance.now();
  //console.log(`parsePLY_start_time (${ply_cellKey}):`, PLYTimes[ply_cellKey]);

  // 确保 ply_data 是 ArrayBuffer
  if (!(ply_data instanceof ArrayBuffer)) {
    console.error(`[${ply_cellKey}] Invalid PLY data type in worker. Expected ArrayBuffer, got ${typeof ply_data}`);
    // 尝试转换，如果它是 Uint8Array (常见情况)
    if (ply_data instanceof Uint8Array) {
      ply_data = ply_data.buffer.slice(ply_data.byteOffset, ply_data.byteOffset + ply_data.byteLength);
    } else {
      // 如果无法转换，则抛出错误
      throw new Error(`[${ply_cellKey}] PLY parsing failed: Invalid data type. Expected ArrayBuffer.`);
    }
  }

  // 解析 PLY 数据
  const plyLoader = new PLYLoader();
  const geometry = plyLoader.parse(ply_data);

  geometry.computeVertexNormals();

  PLYTimes[ply_cellKey] = performance.now() - PLYTimes[ply_cellKey];
  console.log(`parsePLY_time (${ply_cellKey}):`, PLYTimes[ply_cellKey]);

  // 返回包含 geometryData 和 decodeTime 的结构
  return {
    geometryData: {
      frame_id: frame_id,
      cell_id: cell_id,
      positions: geometry.attributes.position.array,
      colors: geometry.attributes.color ? geometry.attributes.color.array : new Float32Array(),
      normals: geometry.attributes.normal ? geometry.attributes.normal.array : new Float32Array(),
    },
    decodeTime: PLYTimes[ply_cellKey]
  };
};

self.decodeDRC = function (frame_id, cell_id, drc_data, cellKey) {
  //console.log(`decodeDRC_start (${cellKey}), FrameID: ${frame_id}, CellID: ${cell_id}, Data size: ${drc_data?.byteLength}`); // 添加日志
  const startTime = performance.now();

  // 检查 drc_data 是否为 ArrayBuffer
  if (!(drc_data instanceof ArrayBuffer)) {
    // 如果不是 ArrayBuffer (例如，可能是 Uint8Array 或其他类型)，尝试转换
    // 注意：如果 video.js 传递过来的已经是 ArrayBuffer，这里可能不需要
    if (drc_data instanceof Uint8Array) {
      drc_data = drc_data.buffer;
    } else {
      // 如果数据是从 fetch response.body.getReader() 逐块拼接的字符串，需要先转码
      // 但看 video.js 的 test_drc，是直接 fetch().arrayBuffer()，所以应该是 ArrayBuffer
      // 这里加一个错误处理以防万一
      console.error(`[${cellKey}] Invalid DRC data type received in worker:`, typeof drc_data);
      throw new Error(`[${cellKey}] DRC 解码失败: 无效的数据类型，需要 ArrayBuffer.`);
    }
  }

  // 初始化DRACO解码器
  const dracoLoader = new DRACOLoader();
  // *** 确保这个路径相对于 Worker 脚本是正确的 ***
  dracoLoader.setDecoderPath('./draco1/');
  dracoLoader.setDecoderConfig({ type: 'wasm' }); // 或 'js'，取决于使用的解码器

  return new Promise((resolve, reject) => {
    dracoLoader.parse(
      drc_data,
      (geometry) => {
        // 解码成功回调
        dracoLoader.dispose(); // 释放解码器资源

        let geometryData;

        // 检查解码出的几何体是否有点数据
        if (!geometry.attributes.position || geometry.attributes.position.count === 0) {
          console.error(`[${cellKey}] DRC 解码后几何体无效或没有顶点`);
          reject(new Error(`[${cellKey}] DRC 解码失败: 解码后的几何体无效或没有顶点.`));
          return;
        }

        // *** 计算法线 ***
        // Draco 点云解码通常不包含法线，需要手动计算
        geometry.computeVertexNormals();

        // 提取数据
        geometryData = {
          frame_id: frame_id,
          cell_id: cell_id,
          positions: geometry.attributes.position.array,
          colors: geometry.attributes.color ? geometry.attributes.color.array : new Float32Array(),
          normals: geometry.attributes.normal ? geometry.attributes.normal.array : new Float32Array(),
        };
        geometry.dispose(); // 释放原始几何体内存


        const decodeTime = performance.now() - startTime;
        //console.log(`decodeDRC_end (${cellKey}), Time: ${decodeTime.toFixed(1)}ms`);

        //console.log(`[${cellKey}] Geometry attributes:`, geometry.attributes); // <<< 添加这行日志，使你的内存爆炸

        // 返回解析数据：
        resolve({
          geometryData: geometryData,
          decodeTime: decodeTime
        });

      },
      (error) => {
        // 解码失败回调
        dracoLoader.dispose(); // 同样需要释放资源
        console.error(`[${cellKey}] DRC解码详细错误:`, error);
        console.error('DRC解码详细错误:', {
          bufferSize: drc_data?.byteLength || 0,
          cellKey,
          errorMessage: error.message,
          errorStack: error.stack // 包含堆栈信息可能更有用
        });
        reject(new Error(`[${cellKey}] DRC解码失败: ${error.message}`));
      }
    );
  }).catch(error => {
    // 捕获 Promise 链中的任何错误
    console.error(`[${cellKey}] decodeDRC Promise chain error:`, error);
    // 确保将错误向上抛出，以便 video.js 能捕获到
    throw error;
  });
};
